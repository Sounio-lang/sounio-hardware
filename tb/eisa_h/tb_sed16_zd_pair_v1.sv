`timescale 1ns/1ps

module tb_sed16_zd_pair_v1;
    localparam [1:0] CLASS_EXACT_ZD_PAIR        = 2'd0;
    localparam [1:0] CLASS_NONZERO_PRODUCT      = 2'd1;
    localparam [1:0] CLASS_INVALID_ZERO_OPERAND = 2'd2;
    localparam [1:0] CLASS_ARITHMETIC_ERROR     = 2'd3;
    localparam [2:0] ERR_NONE                   = 3'd0;
    localparam [2:0] ERR_UNSUPPORTED_DOMAIN     = 3'd2;
    localparam [2:0] ERR_TOO_MANY_NONZERO       = 3'd3;
    localparam [2:0] ERR_OVERFLOW_RISK          = 3'd4;
    localparam logic [255:0] V1_BASIS_NEGATIVE =
        256'hcd4c6726ab8af1e05b523d38979401feccb266d8aa74f01e5aac3cc6966a0000;

    logic clk = 1'b0;
    logic rst_n = 1'b0;
    logic start = 1'b0;
    logic signed [63:0] lhs [0:15];
    logic signed [63:0] rhs [0:15];
    logic ready;
    logic busy;
    logic done;
    logic [1:0] classification;
    logic [2:0] error_code;
    logic product_is_zero;
    wire signed [63:0] product [0:15];
    logic signed [63:0] expected_product [0:15];
    logic [8:0] mac_cycles;
    integer failures = 0;
    integer case_count = 0;
    integer basis_count = 0;
    integer k;

    eisa_h_sed16_zd_pair_v1 dut (
        .clk(clk), .rst_n(rst_n), .start(start), .lhs(lhs), .rhs(rhs),
        .ready(ready), .busy(busy), .done(done), .classification(classification),
        .error_code(error_code), .product_is_zero(product_is_zero),
        .product(product), .mac_cycles(mac_cycles)
    );
    always #5 clk = ~clk;

    task automatic clear_operands;
        integer n;
        begin
            for (n = 0; n < 16; n = n + 1) begin
                lhs[n] = 64'sd0;
                rhs[n] = 64'sd0;
            end
        end
    endtask

    task automatic clear_expected;
        integer n;
        begin
            for (n = 0; n < 16; n = n + 1)
                expected_product[n] = 64'sd0;
        end
    endtask

    function automatic integer golden_basis_sign;
        input integer a;
        input integer b;
        begin
            golden_basis_sign = V1_BASIS_NEGATIVE[(a * 16) + b] ? -1 : 1;
        end
    endfunction

    task automatic run_case;
        input string name;
        input [1:0] expected_class;
        input [2:0] expected_error;
        input integer expected_cycles;
        integer observed_latency;
        integer observed_busy_cycles;
        integer was_busy;
        integer expected_latency;
        begin
            case_count = case_count + 1;
            @(negedge clk);
            if (!ready || busy || done) begin
                $display("FAIL case=%s reason=not-ready-before-accept ready=%0d busy=%0d done=%0d", name, ready, busy, done);
                failures = failures + 1;
            end
            start = 1'b1;
            @(posedge clk); #1;
            start = 1'b0;
            if ((expected_cycles > 0) && (!busy || ready || done)) begin
                $display("FAIL case=%s reason=invalid-accept-handshake ready=%0d busy=%0d done=%0d", name, ready, busy, done);
                failures = failures + 1;
            end
            observed_latency = 0;
            observed_busy_cycles = 0;
            while (!done && observed_latency < 300) begin
                was_busy = busy;
                @(posedge clk); #1;
                observed_latency = observed_latency + 1;
                if (was_busy) observed_busy_cycles = observed_busy_cycles + 1;
                if ((expected_cycles > 0) && (observed_latency == 4)) begin
                    if (ready) begin
                        $display("FAIL case=%s reason=ready-during-busy", name);
                        failures = failures + 1;
                    end
                    start = 1'b1;
                end else if (observed_latency == 5) begin
                    start = 1'b0;
                end
            end
            if (!done) begin
                $display("FAIL case=%s reason=timeout", name);
                failures = failures + 1;
            end
            start = 1'b0;
            expected_latency = (expected_cycles > 0) ? expected_cycles + 1 : 0;
            if ((observed_busy_cycles != expected_cycles) || (observed_latency != expected_latency)) begin
                $display("FAIL case=%s observed_busy=%0d/%0d observed_latency=%0d/%0d", name,
                    observed_busy_cycles, expected_cycles, observed_latency, expected_latency);
                failures = failures + 1;
            end
            if (classification !== expected_class) begin
                $display("FAIL case=%s classification=%0d expected=%0d", name, classification, expected_class);
                failures = failures + 1;
            end
            if (error_code !== expected_error) begin
                $display("FAIL case=%s error=%0d expected=%0d", name, error_code, expected_error);
                failures = failures + 1;
            end
            if (mac_cycles !== expected_cycles[8:0]) begin
                $display("FAIL case=%s mac_cycles=%0d expected=%0d", name, mac_cycles, expected_cycles);
                failures = failures + 1;
            end
            @(posedge clk); #1;
            if (done || busy || !ready) begin
                $display("FAIL case=%s reason=done-not-single-pulse ready=%0d busy=%0d done=%0d", name, ready, busy, done);
                failures = failures + 1;
            end
        end
    endtask

    task automatic expect_component;
        input string name;
        input integer index;
        input signed [63:0] expected;
        begin
            if (product[index] !== expected) begin
                $display("FAIL case=%s product[%0d]=%0d expected=%0d", name, index, product[index], expected);
                failures = failures + 1;
            end
        end
    endtask

    task automatic expect_zero_product;
        input string name;
        integer n;
        begin
            if (!product_is_zero) begin
                $display("FAIL case=%s product_is_zero=0", name);
                failures = failures + 1;
            end
            for (n = 0; n < 16; n = n + 1)
                expect_component(name, n, 64'sd0);
        end
    endtask

    task automatic expect_full_product;
        input string name;
        integer n;
        integer expected_is_zero;
        begin
            expected_is_zero = 1;
            for (n = 0; n < 16; n = n + 1) begin
                expect_component(name, n, expected_product[n]);
                if (expected_product[n] != 0) expected_is_zero = 0;
            end
            if (product_is_zero !== expected_is_zero[0]) begin
                $display("FAIL case=%s product_is_zero=%0d expected=%0d", name, product_is_zero, expected_is_zero);
                failures = failures + 1;
            end
        end
    endtask

    task automatic verify_basis_table;
        integer i;
        integer j;
        integer left_sign;
        integer right_sign;
        string name;
        begin
            for (i = 0; i < 16; i = i + 1) begin
                for (j = 0; j < 16; j = j + 1) begin
                    for (left_sign = -1; left_sign <= 1; left_sign = left_sign + 2) begin
                        for (right_sign = -1; right_sign <= 1; right_sign = right_sign + 2) begin
                            clear_operands();
                            clear_expected();
                            lhs[i] = left_sign;
                            rhs[j] = right_sign;
                            expected_product[i ^ j] = golden_basis_sign(i, j) * left_sign * right_sign;
                            name = $sformatf("basis-e%0d-e%0d-l%0d-r%0d", i, j, left_sign, right_sign);
                            run_case(name, CLASS_NONZERO_PRODUCT, ERR_NONE, 256);
                            expect_full_product(name);
                        end
                    end
                end
            end
            basis_count = case_count;
            case_count = 0;
        end
    endtask

    task automatic verify_reset_in_flight;
        integer n;
        begin
            clear_operands(); lhs[1] = 1; rhs[2] = 1;
            @(negedge clk); start = 1'b1;
            @(posedge clk); #1; start = 1'b0;
            repeat (5) @(posedge clk);
            #1 rst_n = 1'b0;
            #1;
            if (busy || done || !ready || (mac_cycles != 0)) begin
                $display("FAIL reset-in-flight ready=%0d busy=%0d done=%0d mac=%0d", ready, busy, done, mac_cycles);
                failures = failures + 1;
            end
            for (n = 0; n < 16; n = n + 1)
                if (product[n] !== 0) begin
                    $display("FAIL reset-in-flight product[%0d]=%0d", n, product[n]);
                    failures = failures + 1;
                end
            @(negedge clk); rst_n = 1'b1;
        end
    endtask

    initial begin
        clear_operands();
        repeat (3) @(negedge clk);
        rst_n = 1'b1;

        verify_reset_in_flight();
        verify_basis_table();

        clear_operands(); lhs[3] = 1; lhs[10] = 1; rhs[6] = 1; rhs[15] = -1;
        run_case("canonical-zero-divisor-pair", CLASS_EXACT_ZD_PAIR, ERR_NONE, 256);
        expect_zero_product("canonical-zero-divisor-pair");

        clear_operands(); lhs[1] = 1; rhs[2] = 1;
        run_case("basis-orientation-e1-e2", CLASS_NONZERO_PRODUCT, ERR_NONE, 256);
        clear_expected(); expected_product[3] = 1;
        expect_full_product("basis-orientation-e1-e2");

        clear_operands(); lhs[2] = 1; rhs[1] = 1;
        run_case("basis-orientation-e2-e1", CLASS_NONZERO_PRODUCT, ERR_NONE, 256);
        clear_expected(); expected_product[3] = -1;
        expect_full_product("basis-orientation-e2-e1");

        clear_operands(); lhs[3] = 1; lhs[10] = 1; rhs[6] = 1; rhs[15] = 1;
        run_case("same-support-sign-tamper", CLASS_NONZERO_PRODUCT, ERR_NONE, 256);
        clear_expected(); expected_product[5] = 2; expected_product[12] = 2;
        expect_full_product("same-support-sign-tamper");

        clear_operands(); rhs[0] = 1;
        run_case("zero-left-operand", CLASS_INVALID_ZERO_OPERAND, ERR_NONE, 0);

        clear_operands(); lhs[0] = 2; rhs[0] = 1;
        run_case("unsupported-coefficient-two", CLASS_ARITHMETIC_ERROR, ERR_UNSUPPORTED_DOMAIN, 0);

        clear_operands(); lhs[0] = 64'sd4294967296; rhs[0] = 64'sd4294967296;
        run_case("overflow-risk-forged-coefficient", CLASS_ARITHMETIC_ERROR, ERR_OVERFLOW_RISK, 0);

        clear_operands(); rhs[0] = 64'sd4294967296;
        run_case("zero-left-overflow-right", CLASS_ARITHMETIC_ERROR, ERR_OVERFLOW_RISK, 0);

        clear_operands(); lhs[0] = 1; lhs[1] = 1; lhs[2] = 1; rhs[0] = 1;
        run_case("too-many-nonzero-coefficients", CLASS_ARITHMETIC_ERROR, ERR_TOO_MANY_NONZERO, 0);

        clear_operands(); lhs[0] = 64'sd1518500249; rhs[0] = 1;
        run_case("positive-limit-unsupported", CLASS_ARITHMETIC_ERROR, ERR_UNSUPPORTED_DOMAIN, 0);

        clear_operands(); lhs[0] = 64'sd1518500250; rhs[0] = 1;
        run_case("positive-limit-plus-one-overflow", CLASS_ARITHMETIC_ERROR, ERR_OVERFLOW_RISK, 0);

        clear_operands(); lhs[0] = -64'sd1518500249; rhs[0] = 1;
        run_case("negative-limit-unsupported", CLASS_ARITHMETIC_ERROR, ERR_UNSUPPORTED_DOMAIN, 0);

        clear_operands(); lhs[0] = -64'sd1518500250; rhs[0] = 1;
        run_case("negative-limit-minus-one-overflow", CLASS_ARITHMETIC_ERROR, ERR_OVERFLOW_RISK, 0);

        clear_operands(); rhs[0] = -64'sd1518500250;
        run_case("zero-left-negative-overflow", CLASS_ARITHMETIC_ERROR, ERR_OVERFLOW_RISK, 0);

        clear_operands(); lhs[0] = 64'sd1518500250; lhs[1] = 1; lhs[2] = 1; rhs[0] = 2;
        run_case("overflow-precedes-support-and-domain", CLASS_ARITHMETIC_ERROR, ERR_OVERFLOW_RISK, 0);

        if (failures != 0) begin
            $display("EISA_H_ZD_PAIR_RTL_FAIL failures=%0d cases=%0d", failures, case_count);
            $fatal(1);
        end
        $display("EISA_H_ZD_PAIR_RTL_PASS rtl_cases=%0d contract_cases=9 adversarial_cases=6 basis_sign_combinations=%0d interface_cases=1 mac_cycles=256 latency_cycles=257 handshake=VERIFIED", case_count, basis_count);
        $finish;
    end
endmodule
