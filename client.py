import sys
import os
import threading
import random
import glob
from collections import deque
import numpy as np


sys.path.append('gen-py')
sys.path.insert(0, glob.glob('../thrift-0.19.0/lib/py/build/lib*')[0])
from thrift import Thrift
from thrift.transport import TSocket
from thrift.transport import TTransport
from thrift.protocol import TBinaryProtocol
from thrift.server import TServer

from super import super
from super.ttypes import Node
from compute import compute

from ML import mlp

class ClientHandler: 
    def __init__(self, supernode_host='localhost', supernode_port=9091):
        self.supernode_host = supernode_host
        self.supernode_port = supernode_port
        self.connection_point = None
        
    '''
    Connect to another node in the network
    '''
    def connect_to_supernode(self):
        try:
            transport = TSocket.TSocket(self.supernode_host, self.supernode_port)
            transport = TTransport.TBufferedTransport(transport)
            protocol = TBinaryProtocol.TBinaryProtocol(transport)
            client = super.Client(protocol)
            transport.open()
            return client, transport  
        except Exception as e:
            print(f"Failed to connect to node {self.supernode_host}:{self.supernode_port} - {e}")
            return None, None  
    
    '''
    Connect to another node in the network
    '''
    def connect_to_node(self, host, port):
        try:
            transport = TSocket.TSocket(host, port)
            transport = TTransport.TBufferedTransport(transport)
            protocol = TBinaryProtocol.TBinaryProtocol(transport)
            client = compute.Client(protocol)
            transport.open()
            return client, transport  
        except Exception as e:
            print(f"Failed to connect to node {host}:{port} - {e}")
            return None, None  

    '''
    Receive a connection point from supernode to join the network
    '''
    def join_network(self):
        
        host, port = self.unpack_add(node)
        client, transport = self.connect_to_node(host, port)

        if client and transport:
            try:
                client.put_data(fname)  
            # Ensures that connection would be closed
            finally: 
                transport.close() 

  

def main():
    
    # Make socket
    transport = TSocket.TSocket('127.0.0.1', 9091)
    transport = TTransport.TBufferedTransport(transport)
    protocol = TBinaryProtocol.TBinaryProtocol(transport)

    client = super.Client(protocol)

    try:
        # Connect to super node 
        transport.open()

        # Test the supernode functionality
        print("Testing supernode functionality:\n")
        
        # Print initial info
        print("~~~~~~~~~~~~~~~~~~~~~~~~~")
        print("Initial supernode info:")
        print("~~~~~~~~~~~~~~~~~~~~~~~~~")

        print(client.print_info())

        node_id = client.request_join(8000)
        print(f"Requested join with port 8000, got node ID: {node_id}")
        
        # Confirm join
        client.confirm_join(node_id)
        print(f"Confirmed join for node ID: {node_id}")
        
        # Try to get a node
        node_address = client.get_node()
        print(f"Got node address: {node_address}\n")
        
        # Print updated info
        print("~~~~~~~~~~~~~~~~~~~~~~~~~")
        print("Updated supernode info:")
        print("~~~~~~~~~~~~~~~~~~~~~~~~~")
        print(client.print_info())

        # Close!
        transport.close()

    except Thrift.TException as tx:
        print(f"Thrift Exception: {tx.message}")

    '''
    Connect to another node in the network
    '''
    def connect_to_node(self, host, port):
        try:
            transport = TSocket.TSocket(host, port)
            transport = TTransport.TBufferedTransport(transport)
            protocol = TBinaryProtocol.TBinaryProtocol(transport)
            client = compute.Client(protocol)
            transport.open()
            return client, transport  
        except Exception as e:
            print(f"Failed to connect to node {host}:{port} - {e}")
            return None, None  

if name__ == '__main__':
    try:
        main()
    except Thrift.TException as tx:
        print('%s' % tx.message)