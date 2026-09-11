// Self-parity probe for a PIREUS kind=2 operator.
//
// A kind=1 lowering is accepted on bit-exact parity against cd_sigma, because
// a reference exists. A kind=2 operator has no reference. This probe supplies
// what replaces it at the material stratum: the same operator materialised
// twice, by two derivations that share nothing but their arithmetic order.
//
//   REFERENCE path  recomputes the structure coefficient from the phase code
//                   on every term, through the Cayley-Dickson recursion and
//                   the bilinear form, and indexes by a direct XOR.
//   LOWERED path    reads the coefficient from a packed sign table and reaches
//                   the output through the strided lane permutation, as the
//                   emitted lowering does.
//
// Both accumulate each output in ascending right-operand order. That is not an
// accident of implementation: the frozen semantics fix ascending order and
// forbid reassociation, so a divergence here can only be a sign-table or a
// lane-map error, never a summation-order artefact. Allowing the orders to
// differ would measure numerical stability instead, which is a different
// question and is not the one this probe answers.
//
// Agreement establishes that the two materialisations of the operator are the
// same function. It establishes nothing about whether the operator is useful.
// This probe emits no timing and no gain.

#include <array>
#include <bit>
#include <cfenv>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>

namespace {

constexpr int kDimension = 16;
constexpr int kPairs = kDimension * kDimension;

// Cayley-Dickson sign recursion. Transcribed from the frozen Sounio semantics;
// this file defines no algebra of its own.
int cd_sigma(int a, int b, int bits) {
  if (a == 0 || b == 0) return 1;
  if (bits <= 1) return -1;
  const int half = 1 << (bits - 1);
  const bool a_hi = a >= half, b_hi = b >= half;
  const int a_lo = a % half, b_lo = b % half;
  if (!a_hi && !b_hi) return cd_sigma(a_lo, b_lo, bits - 1);
  if (!a_hi && b_hi) return cd_sigma(b_lo, a_lo, bits - 1);
  if (a_hi && !b_hi)
    return b_lo == 0 ? cd_sigma(a_lo, 0, bits - 1) : -cd_sigma(a_lo, b_lo, bits - 1);
  return b_lo == 0 ? -cd_sigma(0, a_lo, bits - 1) : cd_sigma(b_lo, a_lo, bits - 1);
}

// The bilinear phase i^T B j over F2^4.
int bilinear(std::uint16_t code, int x, int y) {
  int s = 0;
  for (int i = 0; i < 4; ++i) {
    if (!((x >> i) & 1)) continue;
    for (int j = 0; j < 4; ++j)
      if ((y >> j) & 1) s ^= (code >> (i * 4 + j)) & 1;
  }
  return s;
}

// Phase code 0 degenerates to cd_sigma exactly.
int sigma(std::uint16_t code, int a, int b) {
  return (cd_sigma(a, b, 4) == -1) ^ bilinear(code, a, b) ? -1 : 1;
}

// Deterministic operands. Fixed bit patterns, never a PRNG: the receipt has to
// be reproducible byte for byte on any host.
double operand(int index, std::uint64_t salt) {
  std::uint64_t z = 0x9E3779B97F4A7C15ULL * (static_cast<std::uint64_t>(index) + 1) + salt;
  z ^= z >> 30; z *= 0xBF58476D1CE4E5B9ULL;
  z ^= z >> 27; z *= 0x94D049BB133111EBULL;
  z ^= z >> 31;
  // Map into [-2, 2) with a bounded exponent, so no term is denormal or
  // infinite and every mismatch is a real disagreement rather than a trap.
  const double unit = static_cast<double>(z >> 11) * (1.0 / 9007199254740992.0);
  return (unit * 4.0) - 2.0;
}

struct Mutation {
  bool corrupt_sign_table = false;   // flip one packed sign bit
  bool corrupt_lane_map = false;     // shift the lane permutation
  bool drop_the_twist = false;       // lower cd_sigma instead of sigma_B
};

// REFERENCE: coefficient recomputed per term, direct XOR index.
void reference_path(std::uint16_t code, const double* x, const double* y, double* z) {
  for (int k = 0; k < kDimension; ++k) {
    double acc = 0.0;
    for (int b = 0; b < kDimension; ++b) {
      const int a = k ^ b;
      acc += static_cast<double>(sigma(code, a, b)) * x[a] * y[b];
    }
    z[k] = acc;
  }
}

// LOWERED: coefficient from a packed table, operands routed through the lane
// permutation and results stored through its inverse.
//
// The lane map has to be load-bearing or its mutation control is decoration.
// It is not enough to permute the order in which outputs are written: that
// leaves every output computing its own index and changes nothing. Here the
// operands are loaded into lane space through the permutation and the results
// are stored back through its inverse, which is what the emitted lowering
// does. The mutation desynchronises the store map from the load map -- the
// specific bug a lane-map error actually is -- rather than renaming both
// consistently, which no arithmetic could detect.
void lowered_path(std::uint16_t code, int stride, int offset, const Mutation& m,
                  const double* x, const double* y, double* z) {
  std::array<signed char, kPairs> table{};
  for (int a = 0; a < kDimension; ++a)
    for (int b = 0; b < kDimension; ++b)
      table[a * kDimension + b] =
          static_cast<signed char>(m.drop_the_twist ? cd_sigma(a, b, 4) : sigma(code, a, b));
  if (m.corrupt_sign_table) table[3 * kDimension + 5] = static_cast<signed char>(-table[3 * kDimension + 5]);

  // Load map and store map. A correct lowering derives both from one stride
  // and offset; the mutation advances the store map by one lane.
  std::array<int, kDimension> load_perm{}, store_inv{};
  const int store_offset = m.corrupt_lane_map ? (offset + 1) % kDimension : offset;
  for (int lane = 0; lane < kDimension; ++lane) {
    load_perm[lane] = (lane * stride + offset) % kDimension;
    store_inv[(lane * stride + store_offset) % kDimension] = lane;
  }

  double xl[kDimension], yl[kDimension], zl[kDimension];
  for (int lane = 0; lane < kDimension; ++lane) {
    xl[lane] = x[load_perm[lane]];
    yl[lane] = y[load_perm[lane]];
  }

  for (int lane = 0; lane < kDimension; ++lane) zl[lane] = 0.0;
  for (int out_lane = 0; out_lane < kDimension; ++out_lane) {
    const int k = load_perm[out_lane];
    double acc = 0.0;
    // Ascending right operand, in the index space the frozen semantics fix.
    for (int b = 0; b < kDimension; ++b) {
      const int a = k ^ b;
      acc += static_cast<double>(table[a * kDimension + b]) * xl[store_inv[a]] * yl[store_inv[b]];
    }
    zl[out_lane] = acc;
  }

  for (int lane = 0; lane < kDimension; ++lane) z[load_perm[lane]] = zl[lane];
}

int compare(const double* p, const double* q, int* first) {
  int mismatching = 0;
  *first = -1;
  for (int k = 0; k < kDimension; ++k) {
    if (std::bit_cast<std::uint64_t>(p[k]) != std::bit_cast<std::uint64_t>(q[k])) {
      if (*first < 0) *first = k;
      ++mismatching;
    }
  }
  return mismatching;
}

int run(std::uint16_t code, int stride, int offset, const Mutation& m, int* first) {
  double x[kDimension], y[kDimension], ref[kDimension], low[kDimension];
  int worst = 0;
  *first = -1;
  for (std::uint64_t trial = 0; trial < 64; ++trial) {
    for (int i = 0; i < kDimension; ++i) {
      x[i] = operand(i, trial * 2 + 0);
      y[i] = operand(i, trial * 2 + 1);
    }
    reference_path(code, x, y, ref);
    lowered_path(code, stride, offset, m, x, y, low);
    int f = -1;
    const int n = compare(ref, low, &f);
    if (n > worst) { worst = n; }
    if (*first < 0 && f >= 0) *first = f;
  }
  return worst;
}

}  // namespace

int main(int argc, char** argv) {
  std::uint16_t code = 1128;
  int stride = 1, offset = 0;
  if (argc > 1) code = static_cast<std::uint16_t>(std::strtoul(argv[1], nullptr, 10));
  if (argc > 2) stride = std::atoi(argv[2]);
  if (argc > 3) offset = std::atoi(argv[3]);

  if (std::fesetround(FE_TONEAREST) != 0) { std::fputs("cannot set FE_TONEAREST\n", stderr); return 2; }
  if (stride < 1 || stride > 15 || stride % 2 == 0) { std::fputs("lane stride must be odd in 1..15\n", stderr); return 2; }

  int first = -1;
  const int mismatching = run(code, stride, offset, Mutation{}, &first);

  int f = -1;
  Mutation sign_mut; sign_mut.corrupt_sign_table = true;
  const int sign_mismatching = run(code, stride, offset, sign_mut, &f);
  Mutation lane_mut; lane_mut.corrupt_lane_map = true;
  const int lane_mismatching = run(code, stride, offset, lane_mut, &f);
  Mutation twist_mut; twist_mut.drop_the_twist = true;
  const int twist_mismatching = run(code, stride, offset, twist_mut, &f);

  std::printf(
      "{\"schema\":1,\"producer_role\":\"OPERATOR_SELF_PARITY\","
      "\"semantic_authority_language\":\"Sounio\",\"kind\":2,"
      "\"phase_code\":%u,\"lane_stride\":%d,\"lane_offset\":%d,"
      "\"dimension\":%d,\"precision\":64,\"trials\":64,"
      "\"reference_derivation\":\"recomputed_per_term\","
      "\"lowered_derivation\":\"packed_sign_table_via_lane_map\","
      "\"shared_accumulation_order\":\"ascending_right_operand\","
      "\"reassociated\":false,\"fma_contracted\":false,"
      "\"rounding_mode\":\"FE_TONEAREST\",\"flush_to_zero\":false,"
      "\"denormals_are_zero\":false,"
      "\"mismatching_lanes\":%d,\"first_mismatch\":%d,"
      "\"sign_mutation_mismatching_lanes\":%d,"
      "\"lane_mutation_mismatching_lanes\":%d,"
      "\"twist_drop_mutation_mismatching_lanes\":%d,"
      "\"twist_is_trivial\":%s,"
      "\"establishes\":\"two_materialisations_agree\","
      "\"claim_ready\":false,\"fp_utility\":\"NOT_ESTABLISHED\","
      "\"result\":\"%s\"}\n",
      static_cast<unsigned>(code), stride, offset, kDimension,
      mismatching, first, sign_mismatching, lane_mismatching, twist_mismatching,
      code == 0 ? "true" : "false",
      (mismatching == 0 && first == -1 && sign_mismatching > 0 &&
       lane_mismatching > 0 &&
       (code == 0 ? twist_mismatching == 0 : twist_mismatching > 0))
          ? "PASS" : "FAIL");
  return 0;
}
