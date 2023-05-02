// SPDX-License-Identifier: UNLICENSED

pragma solidity >=0.7.0 <0.9.0;

import "./OneShotClaim.sol";
import "./Clones.sol";
import "./Ownable.sol";
import {IterableMapping_Address2Address} from "./IterableMapping.sol";
using IterableMapping_Address2Address for IterableMapping_Address2Address.Map;

contract OneShotFactory is Ownable, Clones {

    address public oneShotLibraryAddress;
    IterableMapping_Address2Address.Map private oneshotclaim_contracts;

    constructor(address _oneShotLibraryAddress) {
        oneShotLibraryAddress = _oneShotLibraryAddress;
    }

    function setOneShotLibraryAddress(address _oneShotLibraryAddress) public onlyOwner {
        oneShotLibraryAddress = _oneShotLibraryAddress;
    }
    
    function oneShotExecute (
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
        OneShotClaim(clone).initialize(address(this));

        // call one shot i.e. claim with self destruct
        OneShotClaim(clone).oneShotExecute{ value: msg.value }(
            reward_token_addr, 
            dividend_distribution_function, 
            amount_to_buy,
            tracker_addresses,
            tracker_currencies);
    }

    function oneShotClaim (
        address reward_token_addr                       // reward token address - expected already inserted
    ) public onlyOwner payable
    {
        // check internal contract mapping for this reward token 
        (address payable oneshotclaim_contract_address, bool inserted) = oneshotclaim_contracts.get(reward_token_addr);
        require(inserted, "contract not inserted yet");

        // get necessary info from OneShotClaim contract public interface
        (address _reward_token_addr,
         string memory _dividend_distribution_function,
         uint256 _amount_to_buy,
         address[] memory _tracker_addresses,
         address[] memory _tracker_currencies,
         string memory _claim_function) = OneShotClaim(oneshotclaim_contract_address).getParams();

        // sanity check
        require(reward_token_addr == _reward_token_addr, "contract address mismatch");

        // call oneShotClaim with full argument list
        oneShotClaim(_reward_token_addr, _dividend_distribution_function, _amount_to_buy, _tracker_addresses, _tracker_currencies, _claim_function);

        // send back ether
        refundLeftover(tx.origin);
    }

    function oneShotClaim (
        address reward_token_addr,                      // reward token address
        string memory dividend_distribution_function,   // distribute dividends function name
        uint256 amount_to_buy,                          // minimum number of token holdings
        address[] memory tracker_addresses,             // list of tracker contract addresses
        address[] memory tracker_currencies,            // list of currencies of tracker contracts
        string memory claim_function                    // function for manual claim
    ) public onlyOwner payable
    {
        bool create_clone_ = false;
        bool destroy_previous_ = false;

        // check internal contract mapping for this reward token 
        (address payable oneshotclaim_contract, bool inserted) = oneshotclaim_contracts.get(reward_token_addr);

        if (inserted) {
            // oneShotClaim contract already exists for this reward token
            // check status
            (bool is_listed_for_dividend, bool is_dividend_overflown) = OneShotClaim(oneshotclaim_contract).getDividendStatus();
            is_listed_for_dividend;
            if (is_dividend_overflown) {
                // dividend overflow, destroy contract, transfer reward tokens to new one
                destroy_previous_ = true;
                // new contract needed
                create_clone_ = true;
            }
        } else {
            // no oneShotClaim contract for this reward token
            create_clone_ = true;
        }

        if (create_clone_) {
            // create oneShotClaim contract (== clone)
            address payable new_oneshotclaim_contract = payable(address(clone(oneShotLibraryAddress)));
            // initialize with factory address as owner 
            OneShotClaim(new_oneshotclaim_contract).initialize(address(this));
            // destroy old contract if there was any
            if (destroy_previous_) {
                // transfer reward token to the new contract
                OneShotClaim(oneshotclaim_contract).destroyContr(new_oneshotclaim_contract);
            }
            // update mapping
            oneshotclaim_contract = new_oneshotclaim_contract;
            oneshotclaim_contracts.set(reward_token_addr, oneshotclaim_contract);
            // init new contract data
            OneShotClaim(oneshotclaim_contract).initContract{ value: msg.value }(
                reward_token_addr, 
                dividend_distribution_function, 
                amount_to_buy,
                tracker_addresses,
                tracker_currencies,
                claim_function);
        }

        // call claim
        OneShotClaim(oneshotclaim_contract).oneShotClaim();
        
        // send back ether
        refundLeftover(tx.origin);
    }

    function withdrawClaimedTokens(address addr, bool is_reward_token_addr) public onlyOwner 
    {
        address payable oneshotclaim_contract = payable(addr);
        if (is_reward_token_addr) {
            bool inserted;
            (oneshotclaim_contract, inserted) = oneshotclaim_contracts.get(addr);
            require(inserted, "contract not found");
        }
        OneShotClaim(oneshotclaim_contract).withdrawClaimedTokens(false);
    }

    function destroyContr(address addr, bool is_reward_token_addr) public onlyOwner 
    {
        address payable oneshotclaim_contract = payable(removeFromMapping(addr, is_reward_token_addr));
        OneShotClaim(oneshotclaim_contract).destroyContr();
    }

    function removeFromMapping(address addr, bool is_reward_token_addr) public onlyOwner returns (address)
    {
        address payable oneshotclaim_contract = payable(addr);
        if (is_reward_token_addr) {
            bool inserted;
            (oneshotclaim_contract, inserted) = oneshotclaim_contracts.get(addr);
            require(inserted, "contract not found");
            // remove from oneshotclaim contract mapping
            oneshotclaim_contracts.remove(addr);
        } else {
            // addr == 1SC address 
            for(uint256 i = 0; i < oneshotclaim_contracts.size(); i++) {
                address rew_addr = getRewardTokenAddrAtIndex(i);
                if (addr == get1SCAddr(rew_addr)) {
                    oneshotclaim_contracts.remove(rew_addr);
                    break;
                }
            }
        }
        return oneshotclaim_contract;
    }

    function get1SCAddr(address reward_token_addr) public view returns (address) {
        (address payable oneshotclaim_contract, bool inserted) = oneshotclaim_contracts.get(reward_token_addr);
        if(!inserted) {
            return (0x0000000000000000000000000000000000000000);
        }
        return oneshotclaim_contract;
    }

    function getRewardTokenAddrAtIndex(uint256 index) public view returns (address) {
        if(index >= oneshotclaim_contracts.size()) {
            return (0x0000000000000000000000000000000000000000);
        }
        return oneshotclaim_contracts.getKeyAtIndex(index);
    }

    function getNumberOf1SCContracts() external view returns(uint256) {
        return oneshotclaim_contracts.size();
    }

    function transferAllToken(IERC20 token, address to) public onlyOwner { 
        // transfer all available tokens
        uint256 balance = token.balanceOf(address(this));
        require(balance > 0, "zero balance");
        token.transfer(to, balance);
    }

    function refundLeftover(address to) public onlyOwner {
        (bool success,) = to.call{ value: address(this).balance }("");
        require(success, "refund failed");
    }

    function destroyMe(address payable to) public onlyOwner {
        selfdestruct(to);
    }
}