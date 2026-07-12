`timescale 1ns/1ps

module eisa_h_sed16_zd_pair_v1 (
    input  logic                    clk,
    input  logic                    rst_n,
    input  logic                    start,
    input  logic signed [63:0]      lhs [0:15],
    input  logic signed [63:0]      rhs [0:15],
    output logic                    ready,
    output logic                    busy,
    output logic                    done,
    output logic [1:0]              classification,
    output logic [2:0]              error_code,
    output logic                    product_is_zero,
    output logic signed [63:0]      product [0:15],
    output logic [8:0]              mac_cycles
);
    localparam logic [1:0] CLASS_EXACT_ZD_PAIR       = 2'd0;
    localparam logic [1:0] CLASS_NONZERO_PRODUCT     = 2'd1;
    localparam logic [1:0] CLASS_INVALID_ZERO_OPERAND = 2'd2;
    localparam logic [1:0] CLASS_ARITHMETIC_ERROR    = 2'd3;

    localparam logic [2:0] ERR_NONE                = 3'd0;
    localparam logic [2:0] ERR_UNSUPPORTED_DOMAIN  = 3'd2;
    localparam logic [2:0] ERR_TOO_MANY_NONZERO    = 3'd3;
    localparam logic [2:0] ERR_OVERFLOW_RISK       = 3'd4;

    logic signed [63:0] lhs_latched [0:15];
    logic signed [63:0] rhs_latched [0:15];
    logic signed [63:0] accumulator [0:15];
    logic [3:0] i_index;
    logic [3:0] j_index;
    logic finalize;

    logic validation_overflow;
    logic validation_too_many;
    logic validation_unsupported;
    logic validation_zero;
    logic accumulator_is_zero;
    integer lhs_nonzero_count;
    integer rhs_nonzero_count;
    integer comb_k;
    integer seq_k;

    function automatic integer cd_sigma;
        input integer a;
        input integer b;
        input integer bits;
        integer half;
        integer a_hi;
        integer b_hi;
        integer a_lo;
        integer b_lo;
        begin
            if ((a == 0) || (b == 0)) begin
                cd_sigma = 1;
            end else if (bits <= 1) begin
                cd_sigma = -1;
            end else begin
                half = 1 << (bits - 1);
                a_hi = (a >= half);
                b_hi = (b >= half);
                a_lo = a % half;
                b_lo = b % half;
                if ((a_hi == 0) && (b_hi == 0))
                    cd_sigma = cd_sigma(a_lo, b_lo, bits - 1);
                else if ((a_hi == 0) && (b_hi == 1))
                    cd_sigma = cd_sigma(b_lo, a_lo, bits - 1);
                else if ((a_hi == 1) && (b_hi == 0))
                    cd_sigma = (b_lo == 0) ? cd_sigma(a_lo, 0, bits - 1)
                                           : -cd_sigma(a_lo, b_lo, bits - 1);
                else
                    cd_sigma = (b_lo == 0) ? -cd_sigma(0, a_lo, bits - 1)
                                           : cd_sigma(b_lo, a_lo, bits - 1);
            end
        end
    endfunction

    function automatic signed [63:0] basis_term;
        input signed [63:0] left;
        input signed [63:0] right;
        input [3:0] a;
        input [3:0] b;
        reg signed [63:0] raw;
        begin
            raw = left * right;
            basis_term = (cd_sigma(a, b, 4) < 0) ? -raw : raw;
        end
    endfunction

    always_comb begin
        lhs_nonzero_count = 0;
        rhs_nonzero_count = 0;
        validation_overflow = 1'b0;
        validation_unsupported = 1'b0;
        accumulator_is_zero = 1'b1;
        for (comb_k = 0; comb_k < 16; comb_k = comb_k + 1) begin
            if (lhs[comb_k] != 0) lhs_nonzero_count = lhs_nonzero_count + 1;
            if (rhs[comb_k] != 0) rhs_nonzero_count = rhs_nonzero_count + 1;
            if ((lhs[comb_k] > 64'sd1518500249) || (lhs[comb_k] < -64'sd1518500249) ||
                (rhs[comb_k] > 64'sd1518500249) || (rhs[comb_k] < -64'sd1518500249))
                validation_overflow = 1'b1;
            if (((lhs[comb_k] != 0) && (lhs[comb_k] != 1) && (lhs[comb_k] != -1)) ||
                ((rhs[comb_k] != 0) && (rhs[comb_k] != 1) && (rhs[comb_k] != -1)))
                validation_unsupported = 1'b1;
            if (accumulator[comb_k] != 0) accumulator_is_zero = 1'b0;
        end
        validation_too_many = (lhs_nonzero_count > 2) || (rhs_nonzero_count > 2);
        validation_zero = (lhs_nonzero_count == 0) || (rhs_nonzero_count == 0);
    end

    assign ready = !busy && !finalize;

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            busy <= 1'b0;
            done <= 1'b0;
            finalize <= 1'b0;
            classification <= CLASS_ARITHMETIC_ERROR;
            error_code <= ERR_NONE;
            product_is_zero <= 1'b0;
            mac_cycles <= 9'd0;
            i_index <= 4'd0;
            j_index <= 4'd0;
            for (seq_k = 0; seq_k < 16; seq_k = seq_k + 1) begin
                lhs_latched[seq_k] <= 64'sd0;
                rhs_latched[seq_k] <= 64'sd0;
                accumulator[seq_k] <= 64'sd0;
                product[seq_k] <= 64'sd0;
            end
        end else begin
            done <= 1'b0;
            if (start && ready) begin
                error_code <= ERR_NONE;
                product_is_zero <= 1'b0;
                mac_cycles <= 9'd0;
                i_index <= 4'd0;
                j_index <= 4'd0;
                for (seq_k = 0; seq_k < 16; seq_k = seq_k + 1) begin
                    lhs_latched[seq_k] <= lhs[seq_k];
                    rhs_latched[seq_k] <= rhs[seq_k];
                    accumulator[seq_k] <= 64'sd0;
                    product[seq_k] <= 64'sd0;
                end
                if (validation_overflow) begin
                    classification <= CLASS_ARITHMETIC_ERROR;
                    error_code <= ERR_OVERFLOW_RISK;
                    done <= 1'b1;
                end else if (validation_too_many) begin
                    classification <= CLASS_ARITHMETIC_ERROR;
                    error_code <= ERR_TOO_MANY_NONZERO;
                    done <= 1'b1;
                end else if (validation_unsupported) begin
                    classification <= CLASS_ARITHMETIC_ERROR;
                    error_code <= ERR_UNSUPPORTED_DOMAIN;
                    done <= 1'b1;
                end else if (validation_zero) begin
                    classification <= CLASS_INVALID_ZERO_OPERAND;
                    done <= 1'b1;
                end else begin
                    busy <= 1'b1;
                end
            end else if (busy) begin
                accumulator[i_index ^ j_index] <= accumulator[i_index ^ j_index] +
                    basis_term(lhs_latched[i_index], rhs_latched[j_index], i_index, j_index);
                mac_cycles <= mac_cycles + 9'd1;
                if (j_index == 4'd15) begin
                    j_index <= 4'd0;
                    if (i_index == 4'd15) begin
                        busy <= 1'b0;
                        finalize <= 1'b1;
                    end else begin
                        i_index <= i_index + 4'd1;
                    end
                end else begin
                    j_index <= j_index + 4'd1;
                end
            end else if (finalize) begin
                for (seq_k = 0; seq_k < 16; seq_k = seq_k + 1)
                    product[seq_k] <= accumulator[seq_k];
                product_is_zero <= accumulator_is_zero;
                classification <= accumulator_is_zero ? CLASS_EXACT_ZD_PAIR : CLASS_NONZERO_PRODUCT;
                error_code <= ERR_NONE;
                finalize <= 1'b0;
                done <= 1'b1;
            end
        end
    end
endmodule
