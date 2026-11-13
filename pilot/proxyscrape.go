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

func main() {
	input := flag.String("input", "", "TXT file containing public proxy URLs")
	output := flag.String("output", "", "TXT output path for working proxies")
	threads := flag.Int("threads", 500, "simultaneous checks")
	timeout := flag.Int("timeout-ms", 6000, "timeout for each proxy")
	flag.Parse()
	if err := run(*input, *output, *threads, *timeout); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
}

func load(path string) ([]checker.Proxy, error) {
	file, err := os.Open(path)
	if err != nil {
		return nil, err
	}
	defer file.Close()
	var proxies []checker.Proxy
	seen := make(map[string]bool)
	scanner := bufio.NewScanner(file)
	for scanner.Scan() {
		line := strings.TrimSpace(scanner.Text())
		if line == "" {
			continue
		}
		value, err := url.Parse(line)
		if err != nil || value.User != nil || value.Path != "" || value.RawQuery != "" || value.Fragment != "" {
			return nil, fmt.Errorf("invalid proxy URL on line %d", len(proxies)+1)
		}
		switch value.Scheme {
		case "http", "https", "socks4", "socks5":
		default:
			return nil, fmt.Errorf("unsupported protocol %q", value.Scheme)
		}
		ip, ipErr := netip.ParseAddr(value.Hostname())
		port, portErr := strconv.Atoi(value.Port())
		if ipErr != nil || ip.Zone() != "" || !ip.Unmap().IsGlobalUnicast() || ip.Unmap().IsPrivate() ||
			ip.Unmap().IsLoopback() || netip.MustParsePrefix("100.64.0.0/10").Contains(ip.Unmap()) ||
			portErr != nil || port < 1 || port > 65535 {
			return nil, fmt.Errorf("expected a public IP and port on line %d", len(proxies)+1)
		}
		if seen[line] {
			return nil, fmt.Errorf("duplicate input %q", line)
		}
		seen[line] = true
		proxies = append(proxies, checker.Proxy{
			Host: ip.String(), Port: port, Protocol: value.Scheme, Auth: "none",
		})
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
	if len(proxies) == 0 || threads <= 0 || timeout <= 0 || output == "" {
		return errors.New("a nonempty sample, positive threads and timeout, and output are required")
	}
	ip, err := publicIP()
	if err != nil {
		return err
	}
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Minute)
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
	engine := checker.New(proxies, checker.Options{Threads: threads, Timeout: timeout}, ip, targets, protocols, nil)
	results := make(chan checker.Result, len(proxies))
	progress := make(chan checker.Progress, 1)
	finished := make(chan error, 1)
	started := time.Now()
	go func() { finished <- engine.Run(ctx, results, progress) }()
	counts := make(map[string]int)
	failures := make(map[string]int)
	succeeded := make(map[string]int)
	direct := 0
	withoutExit := 0
	checked := 0
	var working []string
	nextReport := 1000
	for row := range results {
		checked++
		counts[row.Status]++
		for _, detail := range row.Errors {
			failures[detail]++
		}
		if row.Status == "working" {
			switch row.ExitIP {
			case ip:
				direct++
			case "":
				withoutExit++
			}
			for _, protocol := range row.Protocols {
				succeeded[protocol]++
				address := net.JoinHostPort(row.Proxy.Host, strconv.Itoa(row.Proxy.Port))
				working = append(working, protocol+"://"+address)
			}
		}
		if checked >= nextReport {
			fmt.Fprintf(os.Stderr, "Checked %d/%d in %.1fs\n", checked, len(proxies), time.Since(started).Seconds())
			nextReport += 1000
		}
	}
	elapsed := time.Since(started).Seconds()
	if err := <-finished; err != nil {
		return err
	}
	if checked != len(proxies) || counts["cancelled"] != 0 || counts["working"]+counts["failed"] != checked {
		return fmt.Errorf("incomplete test: %d/%d, statuses: %v", checked, len(proxies), counts)
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
