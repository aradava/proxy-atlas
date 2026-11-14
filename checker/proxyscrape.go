package main

import (
	"bufio"
	"context"
	"encoding/json"
	"errors"
	"flag"
	"fmt"
	"io"
	"net"
	"net/http"
	"net/netip"
	"net/url"
	"os"
	"sort"
	"strconv"
	"strings"
	"time"

	"github.com/proxyscrape/checker-backend/internal/checker"
	"github.com/proxyscrape/checker-backend/internal/judges"
	"github.com/proxyscrape/checker-backend/internal/settings"
)

var protocols = []string{"http", "https", "socks4", "socks5"}

type inputProxies struct {
	remoteDNS []checker.Proxy
	localDNS  []checker.Proxy
}

func main() {
	input := flag.String("input", "", "TXT file containing public proxy URLs")
	output := flag.String("output", "", "TXT output path for working proxies")
	threads := flag.Int("threads", 500, "simultaneous checks")
	timeout := flag.Int("timeout-ms", 10000, "timeout for each proxy")
	flag.Parse()
	if err := run(*input, *output, *threads, *timeout); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
}

func load(path string) (inputProxies, error) {
	var proxies inputProxies
	file, err := os.Open(path)
	if err != nil {
		return proxies, err
	}
	defer file.Close()
	seen := make(map[string]bool)
	scanner := bufio.NewScanner(file)
	lineNumber := 0
	for scanner.Scan() {
		lineNumber++
		line := strings.TrimSpace(scanner.Text())
		if line == "" {
			continue
		}
		value, err := url.Parse(line)
		if err != nil || value.User != nil || value.Path != "" || value.RawQuery != "" || value.Fragment != "" {
			return proxies, fmt.Errorf("invalid proxy URL on line %d", lineNumber)
		}
		switch value.Scheme {
		case "http", "https", "socks4", "socks4a", "socks5", "socks5h":
		default:
			return proxies, fmt.Errorf("unsupported protocol %q", value.Scheme)
		}
		ip, ipErr := netip.ParseAddr(value.Hostname())
		port, portErr := strconv.Atoi(value.Port())
		if ipErr != nil || ip.Zone() != "" || !ip.Unmap().IsGlobalUnicast() || ip.Unmap().IsPrivate() ||
			ip.Unmap().IsLoopback() || netip.MustParsePrefix("100.64.0.0/10").Contains(ip.Unmap()) ||
			portErr != nil || port < 1 || port > 65535 {
			return proxies, fmt.Errorf("expected a public IP and port on line %d", lineNumber)
		}
		if seen[line] {
			return proxies, fmt.Errorf("duplicate input %q", line)
		}
		seen[line] = true
		host := ip.String()
		if ip.Is6() {
			// The upstream engine appends the port to Host.
			host = "[" + host + "]"
		}
		proxy := checker.Proxy{
			Host: host, Port: port, Protocol: value.Scheme, Auth: "none",
		}
		switch value.Scheme {
		case "socks4", "socks5":
			proxies.localDNS = append(proxies.localDNS, proxy)
		case "socks4a", "socks5h":
			proxy.Protocol = strings.TrimRight(value.Scheme, "ah")
			proxies.remoteDNS = append(proxies.remoteDNS, proxy)
		default:
			proxies.remoteDNS = append(proxies.remoteDNS, proxy)
		}
	}
	return proxies, scanner.Err()
}

func publicIP() (string, error) {
	client := &http.Client{Timeout: 12 * time.Second}
	response, err := client.Get(settings.DefaultSettings.IP.LookupURL)
	if err != nil {
		return "", err
	}
	defer response.Body.Close()
	body, err := io.ReadAll(io.LimitReader(response.Body, 256))
	if err != nil {
		return "", err
	}
	ip, err := netip.ParseAddr(strings.TrimSpace(string(body)))
	if response.StatusCode != http.StatusOK || err != nil {
		return "", errors.New("the official direct-IP endpoint did not return an IP")
	}
	return ip.String(), nil
}

func run(input, output string, threads, timeout int) error {
	proxies, err := load(input)
	if err != nil {
		return err
	}
	total := len(proxies.remoteDNS) + len(proxies.localDNS)
	if total == 0 || threads <= 0 || timeout <= 0 || output == "" {
		return errors.New("a nonempty input, positive threads and timeout, and output are required")
	}
	ip, err := publicIP()
	if err != nil {
		return err
	}
	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Minute)
	defer cancel()
	defaults := settings.DefaultSettings.Judges
	var items []judges.JudgeItem
	for _, item := range defaults.Items {
		items = append(items, judges.JudgeItem{URL: item.URL, Validate: item.Validate, Active: item.Active})
	}
	targets, err := judges.New(ctx, items, protocols, defaults.Swap)
	if err != nil {
		return err
	}
	started := time.Now()
	counts := make(map[string]int)
	failures := make(map[string]int)
	succeeded := make(map[string]int)
	direct := 0
	withoutExit := 0
	checked := 0
	var working []string
	for _, group := range []struct {
		proxies  []checker.Proxy
		localDNS bool
	}{{proxies.remoteDNS, false}, {proxies.localDNS, true}} {
		if len(group.proxies) == 0 {
			continue
		}
		options := checker.Options{Threads: threads, Timeout: timeout, LocalDNS: group.localDNS}
		engine := checker.New(group.proxies, options, ip, targets, protocols, nil)
		results := make(chan checker.Result, len(group.proxies))
		progress := make(chan checker.Progress, 1)
		finished := make(chan error, 1)
		go func() { finished <- engine.Run(ctx, results, progress) }()
		for row := range results {
			checked++
			counts[row.Status]++
			for _, detail := range row.Errors {
				failures[detail]++
			}
			if row.Status == "working" {
				exit, err := netip.ParseAddr(row.ExitIP)
				switch {
				case err != nil || !exit.IsGlobalUnicast() || exit.IsPrivate():
					withoutExit++
				case row.ExitIP == ip:
					direct++
				default:
					protocol := row.Proxy.Protocol
					if !group.localDNS {
						switch protocol {
						case "socks4":
							protocol = "socks4a"
						case "socks5":
							protocol = "socks5h"
						}
					}
					succeeded[protocol]++
					address := net.JoinHostPort(strings.Trim(row.Proxy.Host, "[]"), strconv.Itoa(row.Proxy.Port))
					working = append(working, protocol+"://"+address)
				}
			}
			if checked%5000 == 0 {
				fmt.Fprintf(os.Stderr, "Checked %d/%d in %.1fs\n", checked, total, time.Since(started).Seconds())
			}
		}
		if err := <-finished; err != nil {
			return err
		}
	}
	elapsed := time.Since(started).Seconds()
	if checked != total || counts["cancelled"] != 0 || counts["working"]+counts["failed"] != checked {
		return fmt.Errorf("incomplete test: %d/%d, statuses: %v", checked, total, counts)
	}
	sort.Strings(working)
	var content string
	if len(working) > 0 {
		content = strings.Join(working, "\n") + "\n"
	}
	if err := os.WriteFile(output, []byte(content), 0600); err != nil {
		return err
	}
	return json.NewEncoder(os.Stdout).Encode(map[string]any{
		"threads": threads, "timeout_ms": timeout, "checked": checked, "seconds": elapsed,
		"statuses": counts, "failure_reasons": failures, "working_by_protocol": succeeded,
		"working_without_exit_ip": withoutExit, "working_with_direct_ip": direct,
		"exported": len(working),
	})
}
