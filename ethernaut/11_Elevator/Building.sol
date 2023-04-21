// SPDX-License-Identifier: MIT
pragma solidity ^0.8.0;

interface Elevator {
    function goTo(uint _floor) external;
}

contract Building {
    bool _called_once;

    function isLastFloor(uint) public returns (bool) {
        bool retval = _called_once;
        _called_once = _called_once == false ? true : false;
        return retval;
    }

    function goToTop(address elevator, uint level) public {
        Elevator(elevator).goTo(level);
    }
}

/*
  Final note:
    You can use the view function modifier on an interface in order to prevent state modifications. The pure modifier also prevents functions from modifying the state. Make sure you read Solidity's documentation and learn its caveats.

    An alternative way to solve this level is to build a view function which returns different results depends on input data but don't modify state, e.g. gasleft().
 */