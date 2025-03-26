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

        #model stored info
        self.weights = {}


    '''
    Hash fname to numerical key value
    '''
    def hash_filename(self, fname):
        return
    

    '''
    Reach the node responsible for the file
    '''
    def reach_destination(self, key):
        if self.pred_id < key <= self.node_id:
            return True
        if self.node_id < self.pred_id and (key > self.pred_id or key <= self.node_id):
            return True
        return False


    '''
    Forward the data to appropriate node 

    Should return addrress of node to allow for recursive calls 
    '''
    def forward_data(self, key):
        for i in range(len(self.finger_ids) - 1, -1, -1):
            if self.finger_ids[i] is not None and self.pred_id < self.finger_ids[i] < key:
                return self.finger_table[i]
        return self.succ
    
    ''' 
    Train model when data reaches node;
    Stores trained weights, V and W for later retrieval
    '''
    def train(self, fname):
        model = mlp()
        if model.init_training_random(fname, _k=26, _h=20):
            V, W = model.get_weights()
            self.weights[fname] = WeightMatrices(V=V.tolist(), W=W.tolist())

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
    
    def unpack_add(self, add):
        host, port = add

        return host, port

    '''
    Place input ML data (filename) into the network;
    Recursively finds the destination node
    '''
    def put_data(self, fname):
        # Hash fname to numerical key value
        key = self.hash_filename(fname)
        
        # Reach destination node
        if self.reach_destination(key):
            print(f"Node {self.node_id} storing and training on file: {fname}")

            # Add to work set
            self.work.add(fname)
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

    def get_model(self, fname):
        '''return a model from a node from an input dataset (filename)'''
        key = self.hash_filename(fname)

        if self.reach_destination(key):
            if fname in self.weights:
                return self.weights[fname]
            if fname in self.work:
                return 'wait'
            return '404'
        
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
            
    def fix_fingers(self):
        '''Makes a node fix its finger table'''
        for i in range(len(self.finger_table)):
            key = (self.node_id + 2**i) % MAX_NODES
            self.finger_ids[i] = key
            self.finger_table[i] = self.forward_data(key)
            
        if not self.succ:
            return

        host, port = self.unpack_add(self.succ)
        client, transport = self.connect_to_node(host, port)
        
        if client and transport:
            try:
                client.fix_fingers()
            finally:
                transport.close()

    def print_info(self):
        '''prints node info'''
        
        print("Network connection info")
        print("Predecessor: ", self.pred)
        print("Successor: ", self.succ)
        print("Finger Table:")
        print("i", "Node", "ID")
        for i in range(len(self.finger_table)):
            print(i, self.finger_table[i], self.finger_ids[i])
            
        print("Hashing info")
        print("Node ID: ", self.node_id)
        print("Files: ")
        for file in self.weights.keys():
            print(file, ", ")
