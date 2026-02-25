"""
NSCOM01 - Machine Project 1
Implementation of Reliable Data Transfer over UDP
Khyle Villorente and Raina Helaga

This module defines the configuration settings for the reliable UDP file transfer project.
"""
SERVER_IP = "127.0.0.1"
SERVER_PORT = 5000
CHUNK_SIZE = 1024
TIMEOUT = 2.0
MAX_RETRIES = 5

SIMULATE_LOSS = False
SIMULATE_CORRUPTION = False
SIMULATE_MISMATCH = False
FAILURE_RATE = 0.3