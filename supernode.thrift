struct Node {
    1: string ip 
    2: i32 port
}

service super {
    # Returns a unique ID to use when joining the network 
    i32 request_join(1: i32 port) 
    
    # Confirm a new node's status in the network 
    void confirm_join(1: i32 node_id) 
    
    # Returns a random connection point (node) to join the network 
    Node get_node() 
    
    # Debugging
    string print_info()
}