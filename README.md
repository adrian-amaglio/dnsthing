dnsthing listens to the docker events stream and maintains a hosts
file in response to containers starting and stopping.  The hosts file
can be consumed by `dnsmasq` for your very own dynamic docker dns
environment.

## Requirements

This probably requires Docker 1.10 or later.

## Synopsis

    usage: dnsthing [-h] [--verbose] [--debug] [--domain DOMAIN]
                    [--hostsfile HOSTSFILE] [--update-command UPDATE_COMMAND]

## Options

- `--verbose`
- `--debug`
- `--domain DOMAIN`, `-d DOMAIN`
- `--hostsfile HOSTSFILE`, `-H HOSTSFILE`
- `--update-command UPDATE_COMMAND`, `-c UPDATE_COMMAND`


## Alternatives
### DNS proxy server
https://github.com/mageddo/dns-proxy-server  
It is a very convenient tool, easy to set-up and it is more maintained.  
Pro: It is all-in-one.  
Cons: It is all-in-one.  
This fork of dnsthings just have one job: watch for docker containers and maintain a list of their addresses.
The DNS proxy server is also implementing a DNS server, a web UI and other things.
