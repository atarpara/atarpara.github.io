---
layout: post
title: "Solady's `sqrt`, derived: 80 bytes of `uint256` square root from first principles"
description: "Deriving every constant in Solady's 80-byte assembly sqrt from first principles — Newton's method, quadratic convergence, and why the optimal magic constant is 1."
tags: [solidity, math, optimization, solady]
---

*Deriving every constant in 80 bytes of assembly from first principles.*

> *tl;dr*: a `uint256` square root in 8 lines of Yul, with every choice justified by math (the \\((n+1)/2\\) formula, no magic multipliers, exactly 6 iterations, and a final correction step). The simple bit-length-based initial guess turns out to be the best you can do — any "magic constant" you might want to multiply by is provably equal to 1.

Take a look at this code:

```solidity
function sqrt(uint256 x) internal pure returns (uint256 z) {
    /// @solidity memory-safe-assembly
    assembly {
        // Step 1: Get the bit position of the most significant bit
        // n = floor(log2(x))
        // For x ≈ 2^n, we know sqrt(x) ≈ 2^(n/2)
        // We use (n+1)/2 instead of n/2 to round up slightly
        // This gives a better initial approximation. This seed gives
        // ε₁ = 0.0607 after one Babylonian step for all inputs. With
        // ε_{n+1} ≈ ε²/2, 6 steps yield 2⁻¹⁶⁰ relative error (>128 correct
        // bits).
        //
        // Formula: z = 2^((n+1)/2) = 2^(floor((n+1)/2))
        // Implemented as: z = 1 << ((n+1) >> 1)
        z := shl(shr(1, sub(256, clz(x))), 1)

        // 6 Babylonian iterations
        z := shr(1, add(z, div(x, z)))
        z := shr(1, add(z, div(x, z)))
        z := shr(1, add(z, div(x, z)))
        z := shr(1, add(z, div(x, z)))
        z := shr(1, add(z, div(x, z)))
        z := shr(1, add(z, div(x, z)))
        // Floor correction
        z := sub(z, lt(div(x, z), z))
    }
}
```

Eight lines of assembly. Eighty bytes of bytecode. This is a complete `uint256` square root — and it's the exact implementation shipped in [Solady's `FixedPointMathLib`](https://github.com/Vectorized/solady/blob/main/src/utils/clz/FixedPointMathLib.sol#L769-L799) (the CLZ-using variant).

But the code raises questions:

- What is that first line doing?
- Why are there exactly 6 copies of the same line?
- Why no multipliers, no magic numbers, no clever bit tricks?
- What's the last line for?

Every Solidity codebase doing AMMs, fixed-point math, or geometric means needs \\(\sqrt{x}\\). People copy this code (or write something similar) without knowing why each piece is there.

In this post, we'll derive every single choice from scratch. By the end, you'll understand each line and know exactly why it can't be made shorter, faster, or simpler without breaking something.

The headline result, hidden in plain sight: **square root has a symmetry that makes the obvious "multiply by a magic constant" optimization useless**. The best constant is 1 — that is, no multiplier at all. We'll see why.

---

## What the code is doing — a quick tour

Before diving into the math, let's read the code from top to bottom.

```solidity
// z0 = 2^(n+1)/2
// where n = log2(x) and log2(x) = 255 - clz(x)
z := shl(shr(1, sub(256, clz(x))), 1)
```

This computes an **initial guess** for \\(\sqrt{x}\\). It's a single line that:

1. Finds the bit length of \\(x\\) (how many bits are needed to represent it).
2. Halves that bit length.
3. Computes 2 raised to that halved bit length.

So if \\(x\\) has 100 bits, the initial guess \\(z\\) is \\(2^{50}\\). This gets us roughly in the right ballpark — close to \\(\sqrt{x}\\) but not exact.

```solidity
z := shr(1, add(z, div(x, z)))
```

This is the **Babylonian update**: replace \\(z\\) with \\((z + x/z) / 2\\). It improves the guess. The `shr(1, ...)` is divide-by-2; the `div(x, z)` is \\(x/z\\); the `add(...)` combines them.

Why does this work? If \\(z\\) is too big, \\(x/z\\) is too small. If \\(z\\) is too small, \\(x/z\\) is too big. Averaging them gets us closer to \\(\sqrt{x}\\). We do this 6 times.

```solidity
z := sub(z, lt(div(x, z), z))
```

This is the **final correction**. Because we're doing integer math (no decimals), the iteration sometimes ends one above the true answer. This line checks if that happened and subtracts 1 if so.

That's the whole thing. Now let's understand *why* each piece looks the way it does.

---

## How much precision do we actually need?

Before deriving anything, let's figure out the target. We want \\(\lfloor\sqrt{x}\rfloor\\) for any \\(x \in [0, 2^{256})\\).

The biggest possible result:

$$\lfloor\sqrt{2^{256} - 1}\rfloor = 2^{128} - 1$$

So the answer always fits in **at most 128 bits**. No matter how clever we get, we never need more than 128 bits of precision.

This is going to be our target throughout. Six iterations is the right number precisely because **6 iterations gets us to 128+ bits of accuracy** — no more, no less. We'll verify this once we have the error analysis.

(Solady's own code comment confirms this: *"6 steps yield \\(2^{-160}\\) relative error (>128 correct bits)"*.)

---

## The Newton iteration

We want \\(z\\) such that \\(z^2 = x\\). Equivalently, find the root of \\(f(z) = z^2 - x\\). Newton-Raphson says:

$$z_{n+1} = z_n - \frac{f(z_n)}{f'(z_n)}$$

With \\(f(z) = z^2 - x\\) and \\(f'(z) = 2z\\):

$$z_{n+1} = z_n - \frac{z_n^2 - x}{2z_n} = \frac{z_n}{2} + \frac{x}{2z_n} = \frac{z_n + x/z_n}{2}$$

This is the **Babylonian method** — 4,000 years older than calculus. The ancient Babylonians figured it out by intuition; Newton gave us the proof.

The intuition: if \\(z_n > \sqrt{x}\\), then \\(x/z_n < \sqrt{x}\\). One overshoots, one undershoots. The average lands closer to the truth than either. Repeat, and you converge quickly.

In the Yul above, each line `z := shr(1, add(z, div(x, z)))` does exactly this: \\((z + x/z) / 2\\).

---

## Ratio: a clean way to measure error

How wrong is our guess? The absolute error \\(|z - \sqrt{x}|\\) doesn't tell the whole story — an error of 0.1 is huge when \\(\sqrt{x} = 1\\) but tiny when \\(\sqrt{x} = 10^{18}\\). We need a **scale-free** measure.

Define the **ratio**:

$$r = \frac{z}{\sqrt{x}}$$

This is a single number that tells us how far off we are, regardless of how big \\(x\\) is:

- \\(r = 1\\) means perfect
- \\(r = 1.1\\) means we're 10% too big
- \\(r = 0.9\\) means we're 10% too small

For Newton's analysis, it's useful to track the **relative error**:

$$\varepsilon = r - 1$$

Same info, shifted so \\(\varepsilon = 0\\) is perfect. Positive \\(\varepsilon\\) means overestimate; negative \\(\varepsilon\\) means underestimate.

### Converting between error and bits of accuracy

A common question: "if my error is \\(\varepsilon\\), how many correct bits do I have?"

The formula is:

$$\text{bits} = -\log_2(|\varepsilon|)$$

In words: take the absolute error, take its log base 2, flip the sign. Each "halving" of the error adds one bit of accuracy.

| \\(\|\varepsilon\|\\) | Bits of accuracy |
|---|---|
| 0.5 | 1 |
| 0.25 | 2 |
| 0.1 | 3.32 |
| 0.01 | 6.64 |
| 0.001 | 9.97 |
| \\(10^{-6}\\) | ~20 |
| \\(10^{-12}\\) | ~40 |
| \\(10^{-25}\\) | ~83 |
| \\(2^{-128}\\) | 128 |

When we say "we need 128 bits of accuracy," that means \\(|\varepsilon| \le 2^{-128} \approx 3 \times 10^{-39}\\). That's our target.

---

## Deriving the ratio recurrence

Newton in terms of \\(z\\):

$$z_{n+1} = \frac{z_n + x/z_n}{2}$$

We want this in terms of \\(r\\). Substitute \\(z = r \cdot \sqrt{x}\\) on both sides:

$$r_{n+1} \cdot \sqrt{x} = \frac{r_n \cdot \sqrt{x} + x / (r_n \cdot \sqrt{x})}{2}$$

The second term inside the parentheses simplifies. Since \\(x = \sqrt{x} \cdot \sqrt{x}\\):

$$\frac{x}{r_n \cdot \sqrt{x}} = \frac{\sqrt{x} \cdot \sqrt{x}}{r_n \cdot \sqrt{x}} = \frac{\sqrt{x}}{r_n}$$

So:

$$r_{n+1} \cdot \sqrt{x} = \frac{\sqrt{x} \cdot (r_n + 1/r_n)}{2}$$

Divide both sides by \\(\sqrt{x}\\):

$$\boxed{r_{n+1} = \frac{r_n + 1/r_n}{2}}$$

**The \\(x\\) disappeared.** The convergence depends only on the ratio, not on how big \\(x\\) is. This is huge — it means whatever worst-case behavior we find applies equally to \\(\sqrt{4}\\) and \\(\sqrt{10^{60}}\\).

Look at this map: \\(g(r) = (r + 1/r) / 2\\). Notice that \\(g(r) = g(1/r)\\). That is: feeding it \\(r = 2\\) gives the same answer as feeding it \\(r = 1/2\\). The map is symmetric — it "folds" the positive numbers around \\(r = 1\\).

**This symmetry is going to rule out a whole class of optimizations** in a moment.

---

## The exact error formula

We've worked with \\(r\\). Now let's substitute \\(r = 1 + \varepsilon\\):

$$r_{n+1} = \frac{(1 + \varepsilon_n) + 1/(1 + \varepsilon_n)}{2}$$

Combine over a common denominator:

$$r_{n+1} = \frac{(1 + \varepsilon_n)^2 + 1}{2(1 + \varepsilon_n)} = \frac{2 + 2\varepsilon_n + \varepsilon_n^2}{2(1 + \varepsilon_n)}$$

Subtract 1 to get \\(\varepsilon_{n+1}\\):

$$\varepsilon_{n+1} = \frac{2 + 2\varepsilon_n + \varepsilon_n^2 - 2 - 2\varepsilon_n}{2(1 + \varepsilon_n)}$$

$$\boxed{\varepsilon_{n+1} = \frac{\varepsilon_n^2}{2(1 + \varepsilon_n)}}$$

This is **exact**, not an approximation. Three things it tells us:

**1. After one Newton step, you're always at an overestimate.** \\(\varepsilon^2\\) is always non-negative, and \\((1 + \varepsilon)\\) is always positive (for valid \\(\varepsilon > -1\\)). So \\(\varepsilon_{n+1} \ge 0\\) no matter what. This is the AM-GM inequality in disguise — the arithmetic mean of two positive numbers is always at least their geometric mean.

**2. The error squares.** For small \\(\varepsilon\\), the formula is roughly \\(\varepsilon_{n+1} \approx \varepsilon^2/2\\). The new error is the *square* of the old, halved. This is called **quadratic convergence**.

**3. Bits roughly double per step.** Taking \\(-\log_2\\) of both sides: \\(\text{bits}_{n+1} \approx 2 \cdot \text{bits}_n + 1\\). Each step doubles your correct bits and adds one extra (from the \\(/2\\)).

That last point determines the iteration count. Starting with \\(b\\) bits of accuracy, after \\(k\\) iterations we have approximately:

$$\text{bits\_after\_k} = 2^k \cdot b + (2^k - 1)$$

We need 128 bits. Solving:

| Iterations \\(k\\) | Required starting bits \\(b\\) |
|---|---|
| 7 | < 1 (basically anything works) |
| 6 | ~1 |
| 5 | ~3 |
| 4 | ~7 |

So 6 iterations needs about 1 bit of starting accuracy. Let's see if our initial guess gives us that.

---

## The initial guess: \\(2^{\lfloor(n+1)/2\rfloor}\\)

In Yul:

```solidity
z := shl(shr(1, sub(256, clz(x))), 1)
```

Reading it:

- `clz(x)` = count of leading zeros in \\(x\\)
- `sub(256, clz(x))` = the bit length of \\(x\\) (= \\(n + 1\\), where \\(n = \lfloor\log_2(x)\rfloor\\))
- `shr(1, ...)` = divide by 2 (floor)
- `shl(..., 1)` = shift `1` left by that many bits, i.e., raise 2 to that power

So \\(z_0 = 2^{\lfloor(n+1)/2\rfloor}\\). In plain English: take the bit length of \\(x\\), halve it (rounding down), and raise 2 to that. This puts us in roughly the right ballpark.

How accurate is it? Let's check by parity of \\(n\\):

| \\(n\\) | \\(z_0\\) | \\(\sqrt{x}\\) range | \\(r_0 = z_0/\sqrt{x}\\) range |
|---|---|---|---|
| even (\\(= 2k\\)) | \\(2^k\\) | \\([2^k, 2^k\sqrt{2})\\) | \\((1/\sqrt{2}, 1]\\) |
| odd (\\(= 2k+1\\)) | \\(2^{k+1}\\) | \\([2^k\sqrt{2}, 2^{k+1})\\) | \\((1, \sqrt{2}]\\) |

Combined: \\(r_0 \in (1/\sqrt{2},\; \sqrt{2}]\\). Worst-case \\(|\varepsilon_0| = \sqrt{2} - 1 \approx 0.4142\\), which in bits is:

$$\text{bits} = -\log_2(0.4142) \approx 1.27$$

That's enough. Six iterations from here will reach 128 bits. We'll verify the trace shortly.

---

## The optimization that doesn't work: magic constants

A natural thought: "what if I multiply the initial guess by some constant \\(c\\) to tighten the worst case?"

If we replace \\(z_0 = 2^{\lfloor(n+1)/2\rfloor}\\) with \\(z_0' = c \cdot 2^{\lfloor(n+1)/2\rfloor}\\), the ratio range becomes \\((c/\sqrt{2},\; c\sqrt{2}]\\). We want to pick \\(c\\) to minimize the worst-case error after one Newton step.

The two extremes give:

$$\varepsilon_{1,\text{high}} \;(\text{from } r = c\sqrt{2}):\quad \frac{(c\sqrt{2} - 1)^2}{2c\sqrt{2}}$$

$$\varepsilon_{1,\text{low}} \;(\text{from } r = c/\sqrt{2}):\quad \frac{(1 - c/\sqrt{2})^2}{2c/\sqrt{2}}$$

Set them equal. Let \\(\beta = c/\sqrt{2}\\):

$$\frac{(2\beta - 1)^2}{2 \cdot 2\beta} = \frac{(1 - \beta)^2}{2\beta}$$

$$(2\beta - 1)^2 = 2(1 - \beta)^2$$

$$4\beta^2 - 4\beta + 1 = 2 - 4\beta + 2\beta^2$$

$$2\beta^2 = 1 \implies \beta = \frac{1}{\sqrt{2}}$$

So \\(c = \beta \cdot \sqrt{2} = 1\\).

**The best constant is 1. That means no multiplier at all.**

This isn't a coincidence — it's the symmetry \\(g(r) = g(1/r)\\) showing up again. The two extremes \\(c\sqrt{2}\\) and \\(c/\sqrt{2}\\) are mirror images around 1, and the Newton map treats them identically when \\(c = 1\\). Any other value of \\(c\\) makes the worst case strictly worse, not better.

This is why Solady's sqrt has no magic multiplier — there's literally no constant that would help. Cube root, on the other hand, has an asymmetric Newton map that *does* benefit from magic constants. You can see this in [Solady's `cbrt`](https://github.com/Vectorized/solady/blob/main/src/utils/clz/FixedPointMathLib.sol#L805-L831): it uses the constant `0x90b5e5` (which decodes to bytes 144, 181, 229) as per-residue multipliers indexed by \\(n \bmod 3\\). That's a separate post.

---

## How many iterations? Six.

Worst case \\(|\varepsilon_0| = \sqrt{2} - 1\\). By symmetry, both cases (even and odd \\(n\\)) produce the same \\(\varepsilon_1\\), which we compute using [the exact error formula](#the-exact-error-formula) derived earlier:

$$\varepsilon_{n+1} = \frac{\varepsilon_n^2}{2(1 + \varepsilon_n)}$$

Plugging in \\(\varepsilon_n = \sqrt{2} - 1\\):

$$\varepsilon_1 = \frac{(\sqrt{2} - 1)^2}{2(1 + \sqrt{2} - 1)} = \frac{3 - 2\sqrt{2}}{2\sqrt{2}} = \frac{3\sqrt{2} - 4}{4} \approx 0.0607$$

Step by step:

- Numerator: \\((\sqrt{2} - 1)^2 = 2 - 2\sqrt{2} + 1 = 3 - 2\sqrt{2}\\)
- Denominator: \\(2(1 + \sqrt{2} - 1) = 2\sqrt{2}\\)
- Divide: \\((3 - 2\sqrt{2}) / (2\sqrt{2})\\)
- Rationalize by multiplying top and bottom by \\(\sqrt{2}\\): \\((3\sqrt{2} - 4) / 4 \approx 0.0607\\)

This matches Solady's code comment exactly: *"This seed gives \\(\varepsilon_1 = 0.0607\\) after one Babylonian step for all inputs."*

The full trace:

| Step | \\(\varepsilon\\) | Bits |
|---|---|---|
| 0 | 0.4142 | 1.27 |
| 1 | 0.0607 | 4.04 |
| 2 | 0.00174 | 9.17 |
| 3 | \\(1.51 \times 10^{-6}\\) | 19.34 |
| 4 | \\(1.14 \times 10^{-12}\\) | 39.67 |
| 5 | \\(6.49 \times 10^{-25}\\) | 80.34 |
| 6 | \\(2.10 \times 10^{-49}\\) | **161.68** ✓ |

Six iterations reach 161 bits — comfortably past our 128-bit target.

**This is why the loop is unrolled exactly 6 times**, not 5 (which leaves us at 80 bits, under target) and not 7 (which is wasted bytecode). Six is the smallest number that works.

The extra buffer between 161 and 128 isn't waste — it's the safety margin that absorbs small integer-arithmetic effects so the final correction step works cleanly.

---

## The floor correction

The last line:

```solidity
z := sub(z, lt(div(x, z), z))
```

What does this do? `lt(div(x, z), z)` evaluates to `1` if \\(x/z < z\\), else `0`. Then we subtract that from \\(z\\).

\\(x/z < z\\) is equivalent to \\(x < z^2\\), which is the same as \\(z > \sqrt{x}\\). So: if \\(z\\) is one above the true floor, subtract 1.

**Why is this needed?** Because of a subtle property of integer Babylonian iteration:

> **If \\(x + 1\\) is a perfect square, the iteration cycles between \\(\lfloor\sqrt{x}\rfloor\\) and \\(\lceil\sqrt{x}\rceil\\).**

Example. Take \\(x = 15\\). True \\(\sqrt{15} \approx 3.873\\). We want \\(\lfloor\sqrt{15}\rfloor = 3\\). Note \\(x + 1 = 16 = 4^2\\) — we're in the cycling case.

If after 6 iterations we landed at \\(z = 4\\), let's see what happens with another step:

```
z = (4 + 15/4)/2 = (4 + 3)/2 = 3   (drops to 3)
z = (3 + 15/3)/2 = (3 + 5)/2 = 4   (back up to 4)
z = (4 + 15/4)/2 = (4 + 3)/2 = 3   (back to 3)
...
```

The iteration alternates forever between 3 and 4 in this case. We always want 3, the floor. The correction handles this: when \\(z = 4\\), we have \\(x/z = 15/4 = 3 < 4 = z\\), so `lt(div(x,z), z) = 1`, and we subtract 1 to get 3. ✓

For non-cycling cases (most \\(x\\)), the iteration converges to \\(\lfloor\sqrt{x}\rfloor\\) exactly, and \\(x/z \ge z\\), so the subtraction is 0 and \\(z\\) is unchanged.

This is documented in [Wikipedia's article on integer square root](https://en.wikipedia.org/wiki/Integer_square_root#Using_only_integer_division), and Solady's own comment cites the same source.

---

## What we proved

Behind 8 lines of assembly, there are 10 non-obvious facts:

1. **Newton-Raphson \\(z_{n+1} = (z + x/z)/2\\) converges to \\(\sqrt{x}\\)** — Newton's theorem.
2. **The iteration in ratio form is \\(r_{n+1} = (r + 1/r)/2\\)** — substitute \\(z = r \cdot \sqrt{x}\\) and simplify.
3. **Initial guess \\(z_0 = 2^{\lfloor(n+1)/2\rfloor}\\) gives \\(|\varepsilon_0| \le \sqrt{2} - 1\\)** — by case analysis on parity of \\(n\\).
4. **The Newton map has symmetry \\(g(r) = g(1/r)\\)** — by inspection.
5. **The optimal multiplier is \\(c = 1\\)** — by the symmetry argument.
6. **Six iterations reach 161 bits from \\(|\varepsilon_0| = \sqrt{2} - 1\\)** — quadratic convergence trace.
7. **128 bits is the right target** — because \\(\lfloor\sqrt{2^{256} - 1}\rfloor = 2^{128} - 1\\).
8. **The iteration ends at \\(\lfloor\sqrt{x}\rfloor\\) or \\(\lfloor\sqrt{x}\rfloor + 1\\)** — AM-GM + integer truncation.
9. **The check `lt(div(x,z), z)` correctly picks the floor** — when \\(z > \sqrt{x}\\), \\(x/z < z\\).
10. **\\(x = 0\\) is handled by EVM's `div(_, 0) = 0`** — incidental but works.

Ten facts. Eight lines. About one per line — which feels right for code that needs to survive a security audit.

---

## Why this matters

Most posts on sqrt say "use Newton-Raphson, here's the code." That leaves the interesting questions on the table:

- **Why 6 iterations and not 4?** — Because \\(|\varepsilon_0| \approx 0.41\\) needs 6 steps to reach 128 bits.
- **Why no magic constant?** — Because the Newton map's symmetry makes \\(c = 1\\) optimal.
- **Why 128 bits of precision?** — Because the maximum result fits in 128 bits.
- **Why is the floor correction needed?** — Because of cycle inputs like \\(x = 15\\).

Each is a separate fact with a separate proof. Together they justify every line of the implementation. Once you understand all four, you can also reason about variations: more iterations if you start with a worse initial guess, fewer if you spend bytecode extracting top bits of \\(x\\).

The reference implementation is [Solady's `sqrt`](https://github.com/Vectorized/solady/blob/main/src/utils/clz/FixedPointMathLib.sol#L769-L799), and the comments in that file (*"\\(\varepsilon_1 = 0.0607\\)"*, *"6 steps yield \\(2^{-160}\\) relative error"*) trace the same derivation we worked through here.

---

## Coming next: cube root

Cube root looks similar:

$$z_{n+1} = \frac{2z + x/z^2}{3}$$

But the \\(1/z^2\\) term **breaks** the symmetry that made sqrt's optimal constant \\(1\\). For cube root, magic constants genuinely help — the optimal per-residue multipliers are \\(144/128\\), \\(181/128\\), \\(228/128\\) (approximately \\(2^{1/6}\\), \\(\sqrt{2}\\), \\(2^{5/6}\\)), and they cut 7 iterations down to 5.

This is exactly what you see in [Solady's `cbrt`](https://github.com/Vectorized/solady/blob/main/src/utils/clz/FixedPointMathLib.sol#L805-L831): the constant `0x90b5e5` packs those three multipliers, indexed by \\(n \bmod 3\\). We'll derive that in the sequel.

Cube root also has a smaller precision target. \\(\lfloor\sqrt[3]{2^{256} - 1}\rfloor \approx 2^{85}\\), so we only need ~85 bits of accuracy, not 128. Smaller target + better initial guess = fewer iterations possible.

The key takeaway transfers: **the symmetry of the Newton map decides whether magic constants help**. For sqrt: useless. For cbrt: essential.