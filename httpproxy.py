#!/usr/bin/env python
# -*- coding: utf-8 -*-

import rocksock
import argparse
import random
from misc import _parse_url, timestamp
import threading
import mysqlite
import socket
import select
import ssl
import string
from os import path
import time

http_verbs = ['CONNECT', 'GET', 'HEAD', 'POST', 'PUT', 'DELETE', 'OPTIONS', 'TRACE', 'PATCH']

class HttpClient():
	def __init__(self, conn, addr):
		self.conn = conn
		self.addr = addr
		self.id = ''.join( random.sample(string.letters, 5))
		print('%s/%s client connected (%s)' % (timestamp(), self.id, self.addr))

	def read_request(self):
		s = ''
		while 1:
			time.sleep(0.1)
			rnrn = s.find('\r\n\r\n')
			if rnrn != -1: break
			r = self.conn.recv(1024)
			if len(r) == 0: return None
			s += r
		return r

	def relay(self, rs, req):

		self.conn.setblocking(0)

		recv = ''
		while 1:
			time.sleep(0.1)
			a,b,c = select.select([rs.sock, self.conn], [], [])
			dst = self.conn if a[0] == rs.sock else rs

			try: buf = a[0].recv(1024)
			except: buf = ''

			if len(buf) == 0: break

			try: dst.send(buf)
			except: break

		self.conn.close()
		rs.disconnect()

class HttpProxy():
	def __init__(self, ip='127.0.0.1', port=8081):
		self.port = port
		self.ip = ip
		self.socket = None

	def setup(self):
		s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
		s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
		s.bind((self.ip, self.port))
		s.listen(args.clients)
		self.socket = s
		print('%s/proxy listening on: %s:%d (base_chain: %s)' % (timestamp(), self.ip, self.port, str(args.base_chain)))

	def wait_client(self):
		conn, addr = self.socket.accept()
		c = HttpClient(conn, addr)
		return c

class BuildChain(threading.Thread):
	def __init__(self, proxylist, host=None, port=None):
		self.port = port
		self.host = host
		self.proxylist = proxylist
		self.ready = False
		threading.Thread.__init__(self)

	def stop(self):
		self.running = False

	def get(self):
		return self.sock, self.chain

	def run(self):
		self.running = True
		while self.running:
			chain = []

			if self.host.endswith('.onion'):
				chain.append(args.tor)
				proxies = [ rocksock.RocksockProxyFromURL(args.tor) ]

			elif self.host.endswith('.i2p'):
				chain.append(args.i2p)
				proxies = [ rocksock.RocksockProxyFromURL(args.i2p) ]

			else:
				pl = self.proxylist

				if args.base_chain:
					chain.append(args.base_chain)
					proxies = [ rocksock.RocksockProxyFromURL(p.strip()) for p in args.base_chain.split(',') ]
				else:
					upstream = None
					proxies = []

				for i in range(args.len - 1):
					choice = random.choice([ p for p in pl ])
					chain.append(choice)
					del( pl[choice] )
					proxies.append( rocksock.RocksockProxyFromURL(choice) )

				lasthop = random.choice([ p for p in pl if not p in chain and pl[p] == 0])
				chain.append(lasthop)
				proxies.append( rocksock.RocksockProxyFromURL( lasthop ) )

			sock = rocksock.Rocksock(host=self.host, port=self.port, ssl=False, proxies=proxies, timeout=args.timeout)

			try: sock.connect()
			except rocksock.RocksockException as e: continue
			except: raise

			self.sock = sock
			self.chain = chain
			self.ready = True
			break

		while self.running: time.sleep(1)

class proxify(threading.Thread):

	def get_verb_line(self, req):
		for line in req.split('\n'):
			verb = line.split(' ')[0].upper()
			if verb in http_verbs:
				return verb, line.split(' ')[1]
		return None, None

	def rebuild_request_for_i2p(self, req):
		for i in req.split('\n'):
			if i.lower().startswith('user-agent'):
				req = req.replace(i, 'User-Agent: MYOB/6.66 (AN/ON)\r')
		return req

	def rebuild_request_for_tor(self, req):
		return req

	def __init__(self, c, proxylist):
		threading.Thread.__init__(self)
		self.c = c
		self.proxylist = proxylist
		self.run()


	def prep_chains(self, proxylist, host, port):
		chains = []
		for i in range(5):
			t = BuildChain(proxylist, host, port)
			t.start()
			chains.append(t)

		while True:
			time.sleep(0.1)
			for t in chains:
				if not t.ready: continue
				print('%s/%s thread %s is ready...' % (timestamp(), self.c.id, t))
				for u in chains:
					if not t == u:
						print('%s/%s stopping thread %s' % (timestamp(), self.c.id, u))
						u.stop()

				rs, chain = t.get()
				return t, rs, chain

	def run(self):
		req = self.c.read_request()
		host = None
		t = None

		if req is not None:

			verb, target = self.get_verb_line(req)

			if verb is not None and target is not None:
				host, port, use_ssl, uri = _parse_url(target)

				if host in blocklist:
					print('%s/%s %s %s [blocked]' % (timestamp(), self.c.id, verb, target))
					host = None

				if host is not None:
					t, rs, chain = self.prep_chains(proxylist, host, port)

					print('%s/%s %s %s [%s]' % (timestamp(), self.c.id, verb, target, ', '.join(chain)))
					if verb == 'CONNECT':
						self.c.conn.send('HTTP/1.0 200 OK\r\n\r\n')
						req = None

					if req is not None:
						if host.endswith('.i2p'): req = self.rebuild_request_for_i2p(req)
						elif host.endswith('.onion'): req = self.rebuild_request_for_tor(req)
						rs.send(req)
					self.c.relay(rs, req)

		if t is not None: t.stop()
		try: self.c.conn.close()
		except: pass
		print('%s/%s client disconnected' % (timestamp(), self.c.id))

if __name__ == '__main__':
	parser = argparse.ArgumentParser()
	parser.add_argument('--base_chain', help="Comma-delimited default chain (default: socks5://127.0.0.1:9050)", type=str, default='socks5://127.0.0.1:9050', required=False)
	parser.add_argument('--ip', help='ip to bind to (default: 127.0.0.1)', type=str, default='127.0.0.1', required=False)
	parser.add_argument('--port', help='port to listen (default: 8081)', type=int, default=8081, required=False)
	parser.add_argument('--database', help="proxy database", type=str, default='proxies.sqlite', required=False)
	parser.add_argument('--len', help="hops to add to default chain (default: 1)", type=int, default=1, required=False)
	parser.add_argument('--timeout', help="connection timeout", type=int, default=10, required=False)
	parser.add_argument('--tor', help="tor upstream (.onion)", type=str,default="socks5://127.0.0.1:9050", required=False)
	parser.add_argument('--i2p', help="i2p upstream (.i2p)", type=str, default="socks5://127.0.0.1:4447", required=False)
	parser.add_argument('--blocklist', help="blocklist (default: blocklist.txt)", type=str, default=None, required=False)
	parser.add_argument('--clients', help="allow X concurrent clients (default: 128)", type=int, default=128, required=False)

	args = parser.parse_args()

	blocklist = dict()
	if args.blocklist and path.exists(args.blocklist):
		with open(args.blocklist,'r') as h:
			for line in h.readlines():
				blocklist[ line.strip() ] = 1
			print('%s/block %d item(s) in list' % (timestamp(), len(blocklist)))

	sql = mysqlite.mysqlite(args.database,str)

	hp = HttpProxy(args.ip, args.port)
	hp.setup()

	while True:
		try: c = hp.wait_client()
		except KeyboardInterrupt: break
		except: raise

		proxylist = {}
		for p in sql.execute("SELECT proto,proxy,mitm from proxylist where failed=0").fetchall():
			proxylist['%s://%s' % (p[0], p[1])] = p[2]

		t = threading.Thread(target=proxify, args=(c, proxylist))
		t.start()
