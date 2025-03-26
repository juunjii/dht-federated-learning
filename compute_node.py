import sys
import time
import random
import glob
from threading import Thread
import os 

sys.path.append('gen-py')
sys.path.insert(0, glob.glob('../thrift-0.19.0/lib/py/build/lib*')[0])

from thrift import Thrift
from thrift.transport import TSocket
from thrift.transport import TTransport
from thrift.protocol import TBinaryProtocol
from thrift.server import TServer


from compute import compute
from compute.ttypes import WeightMatrices
from super import super 
from ML import *
from math import ceil, log2

# Macro for maximum network capacity 
MAX_NODES = 10


class ComputeNodeHandler:
    def __init__(self, host, port, supernode_host='localhost', supernode_port=9090):
        # Connection information to other nodes in network
        self.host = host
        self.port = port
        self.addr = (host, port)
        self.node_id = None

        # Finger table variables
        self.pred = None
        self.pred_id = None
        self.succ = None
        self.succ_id = None
        self.finger_table = [None] * int(ceil(log2(MAX_NODES))) + 1
        self.finger_ids = [None] * int(ceil(log2(MAX_NODES))) + 1

        # Tracks current files used for training
        self.work= set()

        # Supernode information (for joining)
        self.supernode_host = supernode_host
        self.supernode_port = supernode_port


    '''
    Hash fname to numerical key value 
    Key value: 0 - (MAX_NODES -1)
    '''
    def hash_filename(self, fname):
        # Sanitize
        if not fname:
            return None

        return hash(fname) % MAX_NODES
    
    '''
    Using the ID of their predecessor, nodes will accept keys with values 
    greater than their predecessor’s ID and less than or equal to their own ID
    '''
    def check_accept_keys(self, key, pred_id, node_id):
        # Sanitize
        if not key or key < -1:
            return None

        return pred_id < key <= node_id


    '''
    Find the node responsible for a key
    
    '''
    def check_closest_succ(self, key, node_id, succ_id):
        # Sanitize
        if not key or key < -1:
            return None

        return node_id < key <= succ_id



    '''
    Reach the node responsible for the file
    '''
    def reach_destination(self, key):
        # Sanitize
        if not key or key < -1:
            return None
         
        # Single node in network (no predecessors)
        if self.pred_id == self.node_id:
            return True

        return self.check_accept_keys(key, self.pred_id, self.node_id)

    

    '''
    Forward the data to next node until appropriate node is found 

    Should return addrress - (host, port) of node to allow for recursive calls 
    '''
    def forward_data(self, key):
        # Forward to closest successor node 
        if self.check_closest_succ(key, self.node_id, self.succ_id):
            return self.succ
        
        

        pass
    
    ''' 
    Train model when data reaches node;
    Stores trained weights, V and W for later retrieval
    '''
    def train(self, fname):
        pass

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
    Unpack the tuple - self.add = (host, port)
    '''
    def unpack_add(self, add):
        # Sanitize
        if not add:
            return None

        host, port = add

        return host, port

    '''
    Place input ML data (filename) into the network;
    Recursively finds the destination node
    '''
    def put_data(self, fname):
        # Hash fname to numerical key value (0 - MAX_NODES -1)
        key = self.hash_filename(fname)
        
        # Reach destination node
        if self.reach_destination(key):
            print(f"Node {self.node_id} storing and training on file: {fname}")

            # Add to work set
            self.work.add(fname)
            # Start training
            Thread(target=self.train, args=(fname)).start()
        # Continue forwarding 
        else:
            # Return address of node (self.add = (host, port)
            node = self.forward_data(key)
            print(f"Node {self.node_id} forwarding file {fname} to node at {node}")

            host, port = self.unpack_add(node)
            client, transport = self.connect_to_node(host, port)

            if client and transport:
                try:
                    client.put_data(fname)  
                # Ensures that connection would be closed
                finally: 
                    transport.close() 
            

