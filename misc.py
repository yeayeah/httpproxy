# -*- coding: utf-8 -*-

import time

def timestamp():
	return time.strftime('%H:%M:%S', time.gmtime())

def _parse_url(url):
	host = ''
	url_l = url.lower()
	if url_l.startswith('https://'):
		ssl = True
		url = url[8:]
		port = 443
	elif url_l.startswith('http://'):
		ssl = False
		url = url[7:]
		port = 80
	elif url_l.startswith('//'):
		# can happen with a redirect
		ssl = False
		url = url[2:]
		port = -1
	elif url_l.startswith('/'):
		# can happen with a redirect
		url = url[1:]
		port = 0
	else:
		host = url.split(':')[0]
		port = int(url.split(':')[1])
		return host, port, None, url

	if not '/' in url: url = url + '/'

	if port == 0:
		return "", 0, False, url

	port_index = -1
	fixed_amazon_redirect = False
	for i in range(len(url)):
		if url[i] == '?':
			if not fixed_amazon_redirect:
				url = url.replace('?','/?',True)
				fixed_amazon_redirect = True
		if url[i] == ':':
			host = url[:i]
			port_index = i+1
		elif url[i] == '/':
			if port_index >= 0:
				port = int(url[port_index:i])
			else:
				host = url[:i]
			url = url[i:]
			break
	return host, port, ssl, url
