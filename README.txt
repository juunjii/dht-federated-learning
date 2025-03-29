Running system components:

First intialize the super node
super-node.py - Usage: python3 super-node.py <port> <max_nodes>

Next, start up to max_nodes compute nodes. Compute nodes must be declared in compute_nodes.txt.
compute_node.py - Usage: python compute_node.py <host> <port> <supernode_host> <supernode_port>

Finally, run the client to distribute training work.
client.py - Usage: python3 client.py <training_dir> <supernode_host> <supernode_port>