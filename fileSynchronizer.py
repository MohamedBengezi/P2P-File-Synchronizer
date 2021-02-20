#!/usr/bin/python3
# ==============================================================================
# description     :File synchronizer for a peer host.
# usage           :python Skeleton.py trackerIP trackerPort
# python_version  :3.5
# Authors         :Mohamed Bengezi
# ==============================================================================

import socket
import sys
import threading
import json
import time
import os
import ssl
import os.path
import glob
import json
import optparse

ErrorMsg404 = '<html><head></head>>body><h1>404 Not Found</h1></body></html>'


def validate_ip(s):
    """
    Validate the IP address of the correct format
    Arguments:
    s -- dot decimal IP address in string
    Returns:
    True if valid; False otherwise
    """
    a = s.split('.')
    if len(a) != 4:
        return False
    for x in a:
        if not x.isdigit():
            return False
        i = int(x)
        if i < 0 or i > 255:
            return False
    return True


def validate_port(x):
    """Validate the port number is in range [0,2^16 -1 ]
    Arguments:
    x -- port number
    Returns:
    True if valid; False, otherwise
    """
    if not x.isdigit():
        return False
    i = int(x)
    if i < 0 or i > 65535:
        return False
    return True


def get_file_info():
    """ Get file info in the local directory (subdirectories are ignored)
    Return: a JSON array of {'name':file,'mtime':mtime}
    i.e, [{'name':file,'mtime':mtime},{'name':file,'mtime':mtime},...]
    Hint: a. you can ignore subfolders, *.so, *.py, *.dll
          b. use os.path.getmtime to get mtime, and round down to integer
    """
    file_arr = []
    files = [f for f in os.listdir('.') if os.path.isfile(
        f) and os.path.splitext(f)[1] not in ['docx', 'py']]

    for f in files:
        if f.split('.')[1] in ['docx', 'py']:
            continue
        fileObj = {}
        fileObj['name'] = f
        fileObj['mtime'] = int(os.path.getmtime(f))
        file_arr.append(fileObj)

    return file_arr


def check_port_available(check_port):
    """Check if a port is available
    Arguments:
    check_port -- port number
    Returns:
    True if valid; False otherwise
    """
    if str(check_port) in os.popen("netstat -na").read():
        return False
    return True


def get_next_available_port(initial_port):
    """Get the next available port by searching from initial_port to 2^16 - 1
       Hint: You can call the check_port_avaliable() function
             Return the port if found an available port
             Otherwise consider next port number
    Arguments:
    initial_port -- the first port to check

    Return:
    port found to be available; False if no port is available.
    """
    for i in range(initial_port, 2**16):
        if (check_port_available(i)):
            return i
    return False


class FileSynchronizer(threading.Thread):
    def __init__(self, trackerhost, trackerport, port, host='0.0.0.0'):

        threading.Thread.__init__(self)
        # Port for serving file requests
        self.port = port
        self.host = host

        # Tracker IP/hostname and port
        self.trackerhost = trackerhost
        self.trackerport = trackerport

        self.BUFFER_SIZE = 8192

        # Create a TCP socket to communicate with the tracker
        self.client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.client.settimeout(180)

        # Store the message to be sent to the tracker.
        # Initialize to the Init message that contains port number and file info.
        msg = {"port": port, "files": get_file_info()}
        self.msg = json.dumps(msg)

        # Create a TCP socket to serve file requests from peers.
        self.server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

        try:
            self.server.bind((self.host, self.port))
        except socket.error:
            print(('Bind failed %s' % (socket.error)))
            sys.exit()
        self.server.listen(10)

    # Not currently used. Ensure sockets are closed on disconnect
    def exit(self):
        self.server.close()

    # Handle file request from a peer(i.e., send the file content to peers)
    def process_message(self, conn, addr):
        '''
        Arguments:
        self -- self object
        conn -- socket object for an accepted connection from a peer
        addr -- address bound to the socket of the accepted connection
        '''
        # Step 1. read the file name contained in the request through conn
        # Step 2. read content of that file(assumming binary file <4MB), you can open with 'rb'
        # Step 3. send the content back to the requester through conn
        # Step 4. close conn when you are done.
        print('connect to ' + addr[0] + ':' + str(addr[1]))

        try:
            message = conn.recv(2048)
            if not message:
                return
            filename = message.decode()
            print('Client request ' + filename)

            f = open(filename, 'rb')
            msg = f.read()

            for i in range(0, len(msg), self.BUFFER_SIZE):
                end = min(i + self.BUFFER_SIZE, len(msg))
                conn.send(msg[i: end])

        except FileNotFoundError:
            conn.send(b'HTTP/1.1 404 Not Found\r\n')
            conn.send(b'Content-Length: ' + bytes(str(len(ErrorMsg404))))
            conn.send(bytes(ErrorMsg404, 'utf-8'))
        except socket.timeout:
            print('Conn socket timeout')
            return
        except socket.error as e:
            print("Socket error: %s" % e)
            return
        conn.close()

    def run(self):
        self.client.connect((self.trackerhost, self.trackerport))
        t = threading.Timer(2, self.sync)
        t.start()
        print(('Waiting for connections on port %s' % (self.port)))
        while True:
            conn, addr = self.server.accept()
            threading.Thread(target=self.process_message,
                             args=(conn, addr)).start()

    # Send Init or KeepAlive message to tracker, handle directory response message
    # and  request files from peers
    def sync(self):
        print(('connect to:'+self.trackerhost, self.trackerport))
        # Step 1. send Init msg to tracker (Note init msg only sent once)
        # Since self.msg is already initialized in __init__, you can send directly
        try:
            for i in range(0, len(self.msg), self.BUFFER_SIZE):
                end = min(i + self.BUFFER_SIZE, len(self.msg))
                m = self.msg[i:end]
                self.client.send(bytes(m, 'utf-8'))

            # Step 2. now receive a directory response message from tracker
            directory_response_message = self.client.recv(2048).decode()

            if not directory_response_message:
                return

            print('received from tracker:', directory_response_message)

            # Step 3. parse the directory response message. If it contains new or
            # more up-to-date files, request the files from the respective peers.

            resDir = json.loads(directory_response_message)
            localDir = get_file_info()
            local = {}
            for i in localDir:
                local[i['name']] = i['mtime']

            for file in resDir.keys():
                if file not in local.keys() or int(resDir[file]['mtime']) > int(local[file]):
                    print('retrieving %s' % file)
                    peer = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    peer.connect((resDir[file]['ip'], resDir[file]['port']))
                    peer.send(bytes(file, 'utf-8'))
                    f = open(file, 'wb')
                    while True:
                        contents = peer.recv(2048)
                        if not contents:
                            break
                        f.write(contents)
                    f.close()
                    os.utime(
                        file, (int(resDir[file]['mtime']), int(resDir[file]['mtime'])))
                    peer.close()

            # Step 4. construct and send the KeepAlive message

            msg = {"port": self.port}
            self.msg = json.dumps(msg)
            # Step 5. start timer
            t = threading.Timer(5, self.sync)
            t.start()
        except:
            print("Unexpected error:", sys.exc_info()[0])
            raise


if __name__ == '__main__':
    # parse command line arguments
    parser = optparse.OptionParser(usage="%prog ServerIP ServerPort")
    options, args = parser.parse_args()
    if len(args) < 1:
        parser.error("No ServerIP and ServerPort")
    elif len(args) < 2:
        parser.error("No  ServerIP or ServerPort")
    else:
        if validate_ip(args[0]) and validate_port(args[1]):
            tracker_ip = args[0]
            tracker_port = int(args[1])

        else:
            parser.error("Invalid ServerIP or ServerPort")
    # get free port
    synchronizer_port = get_next_available_port(8000)
    synchronizer_thread = FileSynchronizer(
        tracker_ip, tracker_port, synchronizer_port)
    synchronizer_thread.start()
