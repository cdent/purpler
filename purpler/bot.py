# A simple irc bot that connects to a channel, logs what people say
# and parses for [t <nid>] to send that back to the channel.

# Based on
# https://github.com/openstack-infra/gerritbot/blob/master/gerritbot/bot.py
# https://github.com/jaraco/irc/blob/master/scripts/testbot.py

import argparse
import logging
import re
import ssl
import sys
import time

from irc import bot, connection

from purpler import store

COMMANDS = {
    'log': 'show_log',
    'logs': 'show_logs',
    'help': 'show_help',
}
COMMANDER = re.compile('^p!(%s)$' % '|'.join(COMMANDS.keys()))
TRANSCLUDER = re.compile(r'\[t ([A-Za-z0-9]+)\]')

logging.basicConfig(level=logging.DEBUG)

class PurplerBot(bot.SingleServerIRCBot):
    def __init__(self, db_url, server, port, channels, nickname,
                 password, darkchannels, server_password=None):
        if port == 6697:
            factory = connection.Factory(wrapper=ssl.wrap_socket)
            super(PurplerBot, self).__init__([(server, port, server_password)],
                                             nickname, nickname,
                                             connect_factory=factory)
        else:
            super(PurplerBot, self).__init__([(server, port, server_password)],
                                            nickname, nickname)

        self.channel_list = channels
        self.darkchannels = darkchannels
        self.nickname = nickname
        self.password = password
        self.log = logging.getLogger(__name__)
        self.storage = store.Store(db_url)

    def on_nicknameinuse(self, c, e):
        self.log.info('Nick previously in use, recovering.')
        c.nick(c.get_nickname() + "_")
        c.privmsg("nickserv", "identify %s " % self.password)
        c.privmsg("nickserv", "ghost %s %s" % (self.nickname, self.password))
        c.privmsg("nickserv", "release %s %s" % (self.nickname, self.password))
        time.sleep(1)
        c.nick(self.nickname)
        self.log.info('Nick previously in use, recovered.')

    def on_welcome(self, c, e):
        self.log.info('Identifying with IRC server.')
        c.privmsg("nickserv", "identify %s " % self.password)
        self.log.info('Identified with IRC server.')
        for channel in self.channel_list:
            c.join(channel)
            self.log.info('Joined channel %s' % channel)
            time.sleep(0.5)

    def show_help(self, c, e):
        nick = e.source.nick
        c.privmsg(nick, 'p!log to get the URL of the log of the current channel')
        c.privmsg(nick, 'p!logs to get the URL of all available logs')

    def show_log(self, c, e):
        nick = e.source.nick
        channel = e.target.replace('#', '')
        # XXX static url
        c.privmsg(nick, 'log at http://p.anticdent.org/logs/%s' % channel)

    def show_logs(self, c, e):
        nick = e.source.nick
        # XXX static url
        c.privmsg(nick, 'logs at http://p.anticdent.org/logs')

    def on_pubmsg(self, c, e):
        # XXX at the moment we don't see messages that we send so
        # the outgoing message is not logged. Not sure if the fix
        # for that is to see them or just log them.
        nick = e.source.nick
        message = e.arguments[0]

        command = COMMANDER.search(message)
        if command:
            command = command.group(1)
            return getattr(self, COMMANDS[command])(c, e)

        result = TRANSCLUDER.search(message)
        if result:
            guid = result.group(1)
            self.log.debug('saw guid %s', guid)
            outgoing_message = self.storage.get(guid)
            if outgoing_message:
                c.privmsg(e.target, '%s: %s' % (outgoing_message.content, outgoing_message.guid))
        if e.target not in self.darkchannels:
            self.log.debug('Got message %s', message)
            guid = self.storage.put(url=e.target, content='%s: %s' % (nick, message))
            self.log.debug('Logged guid: %s', guid)


def run():

    # TODO: see
    # http://stackoverflow.com/questions/27433316/how-to-get-argparse-to-read-arguments-from-a-file-with-an-option-rather-than-pre
    # for loading args from a file
    parser = argparse.ArgumentParser(description='Run the irc bot')
    parser.add_argument(
        '--db_url',
        dest='db_url',
        default='sqlite:////tmp/purpler',
        help='A db_url that describes where stuff will be stored'
    )
    parser.add_argument(
        '--irc_server',
        dest='server',
        default='chat.freenode.net:6697',
        help='IRC host:port'
    )
    parser.add_argument(
        '--nickname',
        dest='nickname',
        default='purplerbot',
        help='Nickname for the bot'
    )
    parser.add_argument(
        '--password',
        dest='password',
        default='purplerbot',
        help='Password for the bot'
    )
    parser.add_argument(
        '-c', '--channel',
        nargs='?', default=None,
        dest='channels',
        action='append',
        help='With each use add a channel on which the bot should listen. Use # in channel name.'
    )
    parser.add_argument(
        '-n', '--no-log',
        nargs='?', default=None,
        dest='darkchannels',
        action='append',
        help='Channels in the channel list that should not log. Use # in channel name.'
    )
    args = parser.parse_args()

    server, port = args.server.split(':', 1)
    port = int(port)


    bot = PurplerBot(args.db_url, server, port, args.channels,
                     args.nickname, args.password, args.darkchannels)
    bot.start()
