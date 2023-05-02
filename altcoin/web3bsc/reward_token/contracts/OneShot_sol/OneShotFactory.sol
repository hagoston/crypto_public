// SPDX-License-Identifier: UNLICENSED

pragma solidity >=0.7.0 <0.9.0;

import "./OneShot.sol";
import "./Clones.sol";
import "./Ownable.sol";

contract OneShotFactory is Ownable, Clones {

  address public oneShotLibraryAddress;
  event OneShotCloneCreated(address newAddress);

  constructor(address _oneShotLibraryAddress) {
    oneShotLibraryAddress = _oneShotLibraryAddress;
  }

  function setOneShotLibraryAddress(address _oneShotLibraryAddress) public onlyOwner {
    oneShotLibraryAddress = _oneShotLibraryAddress;
  }

  function createOneShotClone (
        address reward_token_addr,                      // reward token address
        string memory dividend_distribution_function,   // distribute dividends function name
        uint256 amount_to_buy,                          // minimum number of token holdings
        address[] memory tracker_addresses,             // list of tracker contract addresses
        address[] memory tracker_currencies)            // list of currencies of tracker contracts 
  public onlyOwner payable
  {
    // create clone
    address payable clone = payable(address(clone(oneShotLibraryAddress)));
    
    // initialize with factory address as owner 
    OneShot(clone).initialize(address(this));

    // call one shot
    OneShot(clone).oneShotExecute{ value: msg.value }(
          reward_token_addr, 
          dividend_distribution_function, 
          amount_to_buy,
          tracker_addresses,
          tracker_currencies);

    // publish clone address
    emit OneShotCloneCreated(clone);
  }
}