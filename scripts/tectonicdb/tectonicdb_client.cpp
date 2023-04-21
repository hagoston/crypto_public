// Client side C/C++ program to demonstrate Socket programming
#include <stdio.h>
#include <sys/socket.h>
#include <arpa/inet.h>
#include <unistd.h>

#include <string>
#include <iostream>
#include <cstring>
#define PORT 9001

int main(int argc, char const *argv[])
{
    int sock = 0, valread;
    struct sockaddr_in serv_addr;
    char buffer[1024] = {0};
    if ((sock = socket(AF_INET, SOCK_STREAM, 0)) < 0)
    {
        printf("\n Socket creation error \n");
        return -1;
    }

    serv_addr.sin_family = AF_INET;
    serv_addr.sin_port = htons(PORT);

    // Convert IPv4 and IPv6 addresses from text to binary form
    if(inet_pton(AF_INET, "192.168.100.42", &serv_addr.sin_addr)<=0)
    {
        printf("\nInvalid address/ Address not supported \n");
        return -1;
    }

    if (connect(sock, (struct sockaddr *)&serv_addr, sizeof(serv_addr)) < 0)
    {
        printf("\nConnection Failed \n");
        return -1;
    }

    std::string message("PING\n");
    char byte_array_msg[4 + message.size()];

    uint32_t bigEndian_msg_size = htonl(message.size());
    memcpy(byte_array_msg, &bigEndian_msg_size, 4);
    memcpy(byte_array_msg+4, message.c_str(), message.size());

    int bytesSent = send(sock , byte_array_msg, 4 + message.size(), 0);
    printf("msg = %s, sent = %d \n", byte_array_msg, bytesSent);

    valread = read( sock , buffer, 1024);
    printf("%s\n",buffer );

    return 0;
}