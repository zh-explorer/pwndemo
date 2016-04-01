import errno
import socket

from ..context import context
from ..log import getLogger
from ..timeout import Timeout
from .sock import sock

log = getLogger(__name__)
#forgive it
black_list = ['gcc','cc','python','sudo','su','wget','nc','curl','ftp',
              'sftp','ssh','vim','vi','nano','passwd','mv','cp','rm','tmp','touch','perl','ip','ifconfig']
class listen(sock):
    """Creates an TCP or UDP-socket to receive data on. It supports
    both IPv4 and IPv6.

    The returned object supports all the methods from
    :class:`pwnlib.tubes.sock` and :class:`pwnlib.tubes.tube`.

    Arguments:
        port(int): The port to connect to.
        bindaddr(str): The address to bind to.
        fam: The string "any", "ipv4" or "ipv6" or an integer to pass to :func:`socket.getaddrinfo`.
        typ: The string "tcp" or "udp" or an integer to pass to :func:`socket.getaddrinfo`.
        timeout: A positive number, None
    """

    def __init__(self, port=0, bindaddr = "0.0.0.0",
                 fam = "any", typ = "tcp",
                 timeout = Timeout.default):
        super(listen, self).__init__(timeout)

        port = int(port)

        if fam == 'any':
            fam = socket.AF_UNSPEC
        elif fam == 4 or fam.lower() in ['ipv4', 'ip4', 'v4', '4']:
            fam = socket.AF_INET
        elif fam == 6 or fam.lower() in ['ipv6', 'ip6', 'v6', '6']:
            fam = socket.AF_INET6
        elif isinstance(fam, (int, long)):
            pass
        else:
            log.error("remote(): family %r is not supported" % fam)

        if typ == "tcp":
            typ = socket.SOCK_STREAM
        elif typ == "udp":
            typ = socket.SOCK_DGRAM
        elif isinstance(typ, (int, long)):
            pass
        else:
            log.error("remote(): type %r is not supported" % typ)

        #log.info('Trying to bind to %s on port %d' % (bindaddr, port))

        for res in socket.getaddrinfo(bindaddr, port, fam, typ, 0, socket.AI_PASSIVE):
            self.family, self.type, self.proto, self.canonname, self.sockaddr = res

            if self.type not in [socket.SOCK_STREAM, socket.SOCK_DGRAM]:
                continue

            #log.info("Trying %s" % self.sockaddr[0])
            listen_sock = socket.socket(self.family, self.type, self.proto)
            listen_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            listen_sock.bind(self.sockaddr)
            self.lhost, self.lport = listen_sock.getsockname()[:2]
            if self.type == socket.SOCK_STREAM:
                listen_sock.listen(1)
            break
        else:
            log.error("Could not bind to %s on port %d" % (bindaddr, port))


        #log.info('Waiting for connections on %s:%s' % (self.lhost, self.lport))

        def accepter():
            while True:
                try:
                    if self.type == socket.SOCK_STREAM:
                        self.sock, rhost = listen_sock.accept()
                        listen_sock.close()
                    else:
                        self.buffer, rhost = listen_sock.recvfrom(4096)
                        listen_sock.connect(rhost)
                        self.sock = listen_sock
                    self.settimeout(self.timeout)
                    break
                except socket.error as e:
                    if e.errno == errno.EINTR:
                        continue
                    log.exception("Socket failure while waiting for connection")
                    self.sock = None
                    return

            self.rhost, self.rport = rhost[:2]
            log.success('Got connection from %s on port %d' % (self.rhost, self.rport))

        self._accepter = context.Thread(target = accepter)
        self._accepter.daemon = True
        self._accepter.start()

    def spawn_process(self, *args, **kwargs):
        def accepter():
            self.wait_for_connection()
            p = super(listen, self).spawn_process(*args, **kwargs)
            p.wait()
            self.close()
        t = context.Thread(target = accepter)
        t.daemon = True
        t.start()

    def wait_for_connection(self):
        """Blocks until a connection has been established."""
        self.sock
        return self

    def __getattr__(self, key):
        if key == 'sock':
            while self._accepter.is_alive():
                self._accepter.join(timeout = 0.1)
            if 'sock' in self.__dict__:
                return self.sock
            else:
                return None
        else:
            return getattr(super(listen, self), key)

    def close(self):
        # since `close` is scheduled to run on exit we must check that we got
        # a connection or the program will hang in the `join` call above
        if self._accepter.is_alive():
            return
        super(listen, self).close()
