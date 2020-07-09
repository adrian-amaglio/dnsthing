#!/usr/bin/python

import argparse
import docker
import logging
import subprocess
import contextlib
import fcntl
from requests.exceptions import ConnectionError

LOG = logging.getLogger(__name__)

_hostfile_start_marker = '# === start dnsthing ==='
_hostfile_end_marker = '# === end dnsthing ==='


@contextlib.contextmanager
def lock_file(fname):
    with open(fname, "r+") as f:
        LOG.debug('acquiring lock on %s', fname)
        fcntl.lockf(f, fcntl.LOCK_EX)
        LOG.debug('acquired lock on %s', fname)

        try:
            yield f
        finally:
            LOG.debug('releasing lock on %s', fname)
            fcntl.lockf(f, fcntl.LOCK_UN)
            LOG.debug('released lock on %s', fname)


class hostRegistry (object):
    def __init__(self, client, hostsfile, domain='docker', onupdate=None):
        self.client = client
        self.domain = domain
        self.hostsfile = hostsfile
        self.onupdate = onupdate
        self.byname = {}
        self.byid = {}

        super(hostRegistry, self).__init__()

    def run(self):
        # Register any existing containers first
        self.scan()

        # Watch for docker events and register/unregister
        # addresses as containers are started and stopped.
        for event in self.client.events(decode=True):
            LOG.debug('event: %s', event)
            if event['Type'] != 'container':
                LOG.debug('ignoring non-container event (%s:%s)',
                          event['Type'], event['Action'])
                continue

            try:
                container = self.client.containers.get(event['id'])
            except docker.errors.NotFound:
                container = {}

            LOG.debug('container: %s', container)
            handler = getattr(self, 'handle_%s' % event['Action'], None)
            if handler:
                LOG.info('handling %s event for %s',
                         event['Action'], event['id'])
                handler(event, container)
            else:
                LOG.debug('not handling %s event for %s',
                          event['Action'], event['id'])

    def handle_start(self, event, container):
        self.register(container)
        self.update_hosts()

    def handle_die(self, event, container):
        self.unregister(container)
        self.update_hosts()

    def scan(self):
        '''Register any existing containers'''

        for container in self.client.containers.list():
            LOG.debug('scan: %s', container)
            self.register(container)

        self.update_hosts()

    def register(self, container):
        '''Register a container.  Iterate over all of the networks to
        which this container is attached, and for each network add the
        name <container_name>.<network_name>.<domnain>.'''

        name = container.name
        if name.startswith('/'):
            name = name[1:]

        if name in self.byname:
            LOG.warn('not registering %s (%s): name already registered to %s',
                     name, container.id, self.byname[name])
            return

        if 'Networks' not in container.attrs['NetworkSettings']:
            LOG.warn('container %s (%s) has no network information',
                     name, container.id)
            return

        this = {
            'name': name,
            'id': container.id,
            'networks': {},
        }

        for nwname, nw in container.attrs['NetworkSettings']['Networks'].items():
            LOG.info('registering container %s network %s ip %s',
                     name, nwname, nw['IPAddress'])
            if nw['IPAddress'] != '':
                this['networks'][nwname] = nw['IPAddress']

        if this['networks']: # If empty dict
            self.byid[container.id] = this
            self.byname[name] = this
        else:
            LOG.debug('Not registering unconnected container (host or none mode).')




    def unregister(self, container):
        '''Remove all entries associated with a given container.'''

        name = container.name
        if name.startswith('/'):
            name = name[1:]

        if container.id in self.byid:
            del self.byid[container.id]
            del self.byname[name]
            LOG.info('unregistered all entries for container %s (%s)',
                     name, container.id)


    def update_hosts(self):
        '''Write out the hosts file and (optionally) trigger the
        onupdate callback.'''

        LOG.info('writing hosts to %s', self.hostsfile)

        with lock_file(self.hostsfile) as f:
            # get all existing entries, strip whitespace (including newline)
            lines = [l.strip() for l in f.readlines()]
            # find dnsthing section and remove it
            try:
                section_start = lines.index(_hostfile_start_marker)
                section_end = lines.index(_hostfile_end_marker)
                del lines[section_start:section_end + 1]
            except ValueError:
                pass
            # create new dnsthing section
            new_section = [
                '%s %s.%s.%s' % (address, name, nwname, self.domain)
                for name, data in self.byname.items()
                for nwname, address in data['networks'].items()
            ]
            new_section = [_hostfile_start_marker] + new_section + [_hostfile_end_marker]
            new_hostsfile = lines + new_section
            # write out the file
            f.seek(0)
            f.truncate()
            f.write('\n'.join(new_hostsfile))

        if self.onupdate:
            self.onupdate()


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument('--verbose', '-v',
                   action='store_const',
                   const='INFO',
                   dest='loglevel')
    p.add_argument('--debug',
                   action='store_const',
                   const='DEBUG',
                   dest='loglevel')
    p.add_argument('--domain', '-d',
                   default='docker')
    p.add_argument('--hostsfile', '-H',
                   default='./hosts')
    p.add_argument('--update-command', '-c')

    p.set_defaults(loglevel='WARN')
    return p.parse_args()


def run_external_command(cmd):
    def runner():
        LOG.info('running external command: %s', cmd)
        subprocess.call(cmd, shell=True)

    return runner


def main():
    args = parse_args()
    logging.basicConfig(level=args.loglevel)
    registry_args = {}

    if args.update_command:
        run_update_command = run_external_command(args.update_command)
        registry_args['onupdate'] = run_update_command

    client = docker.client.from_env()
    registry = hostRegistry(client,
                            args.hostsfile,
                            **registry_args)

    try:
        registry.run()
    except ConnectionError:
        LOG.fatal('urllib could not connect, is docker daemon running?')


if __name__ == '__main__':
    main()
