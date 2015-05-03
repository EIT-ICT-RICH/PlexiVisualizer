__author__ = 'Frank'

import socketserver
import threading
import hashlib
import base64
import os
import json

connectedclients = {}
connectedSchedulers = {}
client_schedulers = {}#key: client identity, value: list of requested schedulers
scheduler_clients = {}#key: scheduler identity, value: list of sockets that listen to this scheduler

def chunks(l, n):
	#Yield successive n-sized chunks from l
	for i in range(0, len(l), n):
		yield l[i:i+n]


class ThreadedServerHandler(socketserver.BaseRequestHandler):

	def handle(self):
		# addr = self.request.getpeername()[0]
		self.data = self.request.recv(1024)
		request = str(self.data, "utf-8")
		# print("request:\n" + request)
		if "Upgrade: websocket" in request:

			self.HandShake(request)
			self.client = "web"

			#get the identity
			data = self.parse_frame()
			self.identity = str(data, "utf-8")
			#register the client
			connectedclients[self.identity] = self
			#register the requested schedulers
			data = str(self.parse_frame(), "utf-8")
			print("requested schedulers: ")
			print(data)
			client_schedulers[self.identity] = json.loads(data)
			for shd in client_schedulers[self.identity]:
				try:
					scheduler_clients[shd].append(self)
				except:
					scheduler_clients[shd] = []
					scheduler_clients[shd].append(self)

			#wait for requests
			print("New connection(webclient): " + self.identity)
			while True:
				try:
					data = self.parse_frame()
					if data == "":
						continue
					data = str(data, "utf-8")
					if os.path.isfile(data + ".dot"):
						with open(data + ".dot", "r") as graphfile:
							content = graphfile.read()
						self.send(self.request, content)
					else:
						print(self.identity + " requested nonexisting graph " + data)
				except:
					print("\nClient from " + self.identity + " disconnected")
					return
		else:
			#register this scheduler
			self.client = "scheduler"
			connectedSchedulers[request] = self
			self.identity = request
			if self.identity not in scheduler_clients:
				scheduler_clients[self.identity] = []
			self.identity = request
			print("New connection(scheduler): " + self.identity)
			while True:
				data = str(self.request.recv(1024), "utf-8")
				if data == "":
					continue
				#for each listener, send the dot file
				print("dotfile received:")
				print(data)
				for client in scheduler_clients[self.identity]:
					self.send(client.request, data)

	def HandShake(self, request):
		specificationGUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
		websocketkey = ""
		protocol = ""
		for line in request.split("\r\n"):
			if "Sec-WebSocket-Key:" in line:
				websocketkey = line.split(" ")[1]
			elif "Sec-WebSocket-Protocol" in line:
				protocol = line.split(":")[1].strip().split(",")[0].strip()
			elif "Origin" in line:
				self.origin = line.split(":")[0]

		# print("websocketkey: " + websocketkey + "\n")
		fullKey = hashlib.sha1(websocketkey.encode("utf-8") + specificationGUID.encode("utf-8")).digest()
		acceptKey = base64.b64encode(fullKey)
		# print("acceptKey: " + str(acceptKey, "utf-8") + "\n")
		if protocol != "":
			handshake = "HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Protocol: " + protocol + "\r\nSec-WebSocket-Accept: " + str(acceptKey, "utf-8") + "\r\n\r\n"
		else:
			handshake = "HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Accept: " + str(acceptKey, "utf-8") + "\r\n\r\n"
		# print(handshake.strip("\n"))
		self.request.send(bytes(handshake, "utf-8"))

	def send(self, socket, data):
		print("sending data: " + data)
		if len(data) < 126:
			socket.sendall(self.create_frame(data))
			return
		c = chunks(data, 125)
		socket.sendall(self.create_frame("$STARTGRAPH"))
		for co in c:
			self.request.sendall(self.create_frame(co))
		socket.sendall(self.create_frame("$ENDGRAPH"))


	def create_frame(self, data):
		# pack bytes for sending to client
		frame_head = bytearray(2)

		# set final fragment
		frame_head[0] = self.set_bit(frame_head[0], 7)

		# set opcode 1 = text
		frame_head[0] = self.set_bit(frame_head[0], 0)

		# payload length
		# assert len(data) < 126, "haven't implemented that yet"
		frame_head[1] = len(data)

		# add data
		frame = frame_head + data.encode('utf-8')
		# print("frame crafted for message " + data + ":")
		# print(list(hex(b) for b in frame))
		return frame

	def is_bit_set(self, int_type, offset):
		mask = 1 << offset
		return not 0 == (int_type & mask)

	def set_bit(self, int_type, offset):
		return int_type | (1 << offset)

	def bytes_to_int(self, data):
		# note big-endian is the standard network byte order
		return int.from_bytes(data, byteorder='big')

	def parse_frame(self):
		"""receive data from client"""
		s = self.request
		# read the first two bytes
		frame_head = s.recv(2)

		# very first bit indicates if this is the final fragment
		# print("final fragment: ", self.is_bit_set(frame_head[0], 7))

		# bits 4-7 are the opcode (0x01 -> text)
		# print("opcode: ", frame_head[0] & 0x0f)

		# mask bit, from client will ALWAYS be 1
		assert self.is_bit_set(frame_head[1], 7)

		# length of payload
		# 7 bits, or 7 bits + 16 bits, or 7 bits + 64 bits
		payload_length = frame_head[1] & 0x7F
		if payload_length == 126:
			raw = s.recv(2)
			payload_length = self.bytes_to_int(raw)
		elif payload_length == 127:
			raw = s.recv(8)
			payload_length = self.bytes_to_int(raw)
		# print('Payload is {} bytes'.format(payload_length))

		#masking key
		#All frames sent from the client to the server are masked by a
		#32-bit nounce value that is contained within the frame

		masking_key = s.recv(4)
		# print("mask: ", masking_key, self.bytes_to_int(masking_key))

		# finally get the payload data:
		masked_data_in = s.recv(payload_length)
		data = bytearray(payload_length)

		# The ith byte is the XOR of byte i of the data with
		# masking_key[i % 4]
		for i, b in enumerate(masked_data_in):
			data[i] = b ^ masking_key[i%4]
		return data

class ThreadedTCPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
	pass

HOST = "192.168.137.211"
PORT = 600
server = ThreadedTCPServer((HOST, PORT), ThreadedServerHandler)
server_thread = threading.Thread(target=server.serve_forever)
server_thread.daemon = True
server_thread.start()
print("server started, waiting for connections...")

while True:
	pass
