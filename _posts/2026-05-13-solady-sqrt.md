---
layout: post
title: "Solady's sqrt, derived: 80 bytes of uint256 square root from first principles"
description: "Deriving every constant in Solady's 80-byte assembly sqrt from first principles — Newton's method, quadratic convergence, and why the optimal magic constant is 1."
tags: [solidity, math, optimization, solady]
---

> *Special thanks to [Duncan](https://github.com/duncancmt) for formally verifying this implementation in [0x-settler#511](https://github.com/0xProject/0x-settler/pull/511).*

A `uint256` square root in Solidity takes exactly 8 lines of Yul. The implementation shipped in Solady's `FixedPointMathLib` is 80 bytes of bytecode, uses no magic multipliers, unrolls a loop exactly 6 times, and finishes with a single floor correction.

In this post, we are going to derive every single choice from scratch, using nothing fancier than high-school algebra. We will prove why the simple bit-length-based initial guess is the best you can do, and why any "magic constant" you might want to multiply it by is provably equal to 1.

Take a look at the code:

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

Eight lines of assembly. Eighty bytes. Let's break down exactly why it can't be shorter, faster, or simpler.

---

## A quick tour of the code

Before diving into the math, here is what each part is doing.

```solidity
z := shl(shr(1, sub(256, clz(x))), 1)
```

This first line computes an **initial guess** for \\(\sqrt{x}\\). It does three things:

1. Finds the bit length of \\(x\\) (how many bits are needed to represent it).
2. Halves that bit length.
3. Computes 2 raised to that halved bit length.

If \\(x\\) has 100 bits, the initial guess \\(z\\) is \\(2^{50}\\). This gets us close to \\(\sqrt{x}\\), but it's not exact.

```solidity
z := shr(1, add(z, div(x, z)))
```

This is the **Babylonian update**. It replaces \\(z\\) with \\((z + x/z) / 2\\). If \\(z\\) is too big, \\(x/z\\) is too small. If \\(z\\) is too small, \\(x/z\\) is too big. Averaging them gets us closer to the true square root. The code repeats this line exactly 6 times.

```solidity
z := sub(z, lt(div(x, z), z))
```

This is the **final correction**. Because we are doing integer math without decimals, the iteration sometimes ends one number higher than the true answer. This line checks if that happened, and subtracts 1 if it did.

That's the whole algorithm. Now let's understand the math behind it.

---

## Why 128 bits of precision is exactly enough

We want to find \\(\lfloor\sqrt{x}\rfloor\\) for any \\(x\\) up to \\(2^{256} - 1\\). How big can the answer get?

The biggest input is \\(x = 2^{256} - 1\\). Its square root is just under \\(2^{128}\\) — because \\((2^{128})^2 = 2^{256}\\). So:

$$
\lfloor\sqrt{2^{256} - 1}\rfloor = 2^{128} - 1
$$

The answer always fits in **at most 128 bits**. We never need more than 128 bits of precision. That's our target.

Spoiler: 6 iterations gets us exactly there, with a little safety margin.

---

## The Babylonian method: a 4000-year-old trick

Here is an ancient algorithm. To find \\(\sqrt{x}\\):

1. Guess any positive number \\(z\\).
2. Compute \\((z + x/z) / 2\\). This is your new guess.
3. Repeat until you're happy.

The Babylonians used this 4000 years ago, long before calculus existed. Why does it work?

**The intuition.** Suppose you're trying to find \\(\sqrt{100}\\), and you guess \\(z = 25\\). That's way too big. Now compute \\(x/z = 100/25 = 4\\). That's way too small.

But here's the thing: the *product* of these two numbers is always exactly \\(x\\). \\(25 \times 4 = 100\\). So whenever one is too big, the other is too small by a complementary amount. Their average lands much closer to \\(\sqrt{x}\\) than either one alone.

\\((25 + 4)/2 = 14.5\\), which is closer to the true answer of 10 than either 25 or 4 was. Run the iteration again: \\(100/14.5 \approx 6.9\\), average gives \\(\approx 10.7\\). Two more steps and you've nailed it.

### The same formula, from calculus

If you have calculus, here's the modern derivation. We want \\(z\\) such that \\(z^2 = x\\), which means finding where the function \\(f(z) = z^2 - x\\) equals zero. Newton-Raphson says: from any guess \\(z_n\\), the next guess is

$$
z_{n+1} = z_n - \frac{f(z_n)}{f'(z_n)}
$$

(If derivatives are new to you: \\(f'(z)\\) just means the slope of \\(f\\) at the point \\(z\\). For \\(f(z) = z^2 - x\\), the slope is \\(f'(z) = 2z\\). You can take this on faith or look up the power rule.)

Substituting:

$$
z_{n+1} = z_n - \frac{z_n^2 - x}{2z_n}
$$

Let's simplify. Get a common denominator on the right:

$$
z_{n+1} = \frac{2z_n^2 - (z_n^2 - x)}{2z_n} = \frac{z_n^2 + x}{2z_n}
$$

Split the fraction:

$$
z_{n+1} = \frac{z_n^2}{2z_n} + \frac{x}{2z_n} = \frac{z_n}{2} + \frac{x}{2z_n} = \frac{1}{2}\left(z_n + \frac{x}{z_n}\right)
$$

That's exactly the Babylonian formula. The ancients beat Newton by ~3500 years.

In the Yul code, the line `z := shr(1, add(z, div(x, z)))` is doing precisely \\((z + x/z)/2\\) — `div(x, z)` is \\(x/z\\), `add(z, ...)` adds it to \\(z\\), and `shr(1, ...)` shifts right by 1 bit, which is division by 2.

---

## Measuring error with the ratio

How wrong is our guess? The absolute error \\(\lvert z - \sqrt{x} \rvert\\) doesn't help much. Being off by 0.1 is huge if the true answer is 1, but tiny if the true answer is a billion. We need a scale-free measure.

Let's define the **ratio**:

$$
r = \frac{z}{\sqrt{x}}
$$

This tells us how far off we are, regardless of the size of \\(x\\):

- \\(r = 1\\) means perfect.
- \\(r = 1.1\\) means we are 10% too big.
- \\(r = 0.9\\) means we are 10% too small.

We can also track the **relative error**:

$$
\varepsilon = r - 1
$$

Here, \\(\varepsilon = 0\\) is perfect. Positive means overestimate, negative means underestimate.

How does error translate to bits of accuracy? Each time you cut the error in half, you gain one bit of accuracy. So:

$$
\text{bits of accuracy} = -\log_2(\lvert\varepsilon\rvert)
$$

The minus sign is there because errors are less than 1, which makes their log negative. A few reference values:

| \\(\lvert\varepsilon\rvert\\) | Bits of accuracy |
|---|---|
| 0.5 | 1 |
| 0.25 | 2 |
| 0.01 | 6.64 |
| \\(10^{-6}\\) | ~20 |
| \\(10^{-12}\\) | ~40 |
| \\(2^{-128}\\) | 128 |

To get 128 bits of accuracy, we need \\(\lvert\varepsilon\rvert \le 2^{-128} \approx 3 \times 10^{-39}\\). That's a *tiny* number, but we'll see it's achievable.

---

## Rewriting the iteration in terms of the ratio

This step is going to seem like a random change of variables, but it pays off enormously. We're going to rewrite the Newton iteration so it doesn't mention \\(x\\) at all.

Start with:

$$
z_{n+1} = \frac{z_n + x/z_n}{2}
$$

Substitute \\(z = r \cdot \sqrt{x}\\) on both sides. On the left:

$$
z_{n+1} = r_{n+1} \cdot \sqrt{x}
$$

On the right, the first term becomes \\(r_n \cdot \sqrt{x}\\). The second term \\(x/z_n\\) becomes \\(x / (r_n \cdot \sqrt{x})\\). Simplify this: since \\(x = \sqrt{x} \cdot \sqrt{x}\\), we get

$$
\frac{x}{r_n \sqrt{x}} = \frac{\sqrt{x} \cdot \sqrt{x}}{r_n \sqrt{x}} = \frac{\sqrt{x}}{r_n}
$$

Putting it all together:

$$
r_{n+1} \cdot \sqrt{x} = \frac{r_n \cdot \sqrt{x} + \sqrt{x}/r_n}{2} = \sqrt{x} \cdot \frac{r_n + 1/r_n}{2}
$$

Divide both sides by \\(\sqrt{x}\\):

$$
r_{n+1} = \frac{r_n + 1/r_n}{2}
$$

**Look at what just happened: \\(x\\) disappeared.** The recurrence for the ratio is completely independent of \\(x\\). The way our error shrinks for \\(\sqrt{4}\\) is identical to the way it shrinks for \\(\sqrt{10^{60}}\\). One worst-case analysis covers every input.

### A symmetry hiding in the formula

Define \\(g(r) = (r + 1/r)/2\\), the function the iteration applies to the ratio. Notice something: \\(g(r) = g(1/r)\\). Let's check with numbers:

- \\(g(2) = (2 + 0.5)/2 = 1.25\\)
- \\(g(1/2) = (0.5 + 2)/2 = 1.25\\)

Same answer. Try any other pair:

- \\(g(4) = (4 + 0.25)/2 = 2.125\\)
- \\(g(1/4) = (0.25 + 4)/2 = 2.125\\)

The function treats \\(r\\) and \\(1/r\\) identically. Intuitively: if you're off by a factor of 2 in one direction, or off by a factor of 2 in the other direction, Newton's method corrects you the same amount either way.

**This symmetry is the thing that's going to kill the magic-constant optimization.** Hold that thought.

---

## The exact error formula, step by step

We have the recurrence in terms of \\(r\\). Now let's write it in terms of the error \\(\varepsilon\\). Substitute \\(r_n = 1 + \varepsilon_n\\) into \\(r_{n+1} = (r_n + 1/r_n)/2\\):

$$
1 + \varepsilon_{n+1} = \frac{(1 + \varepsilon_n) + \dfrac{1}{1 + \varepsilon_n}}{2}
$$

Combine the right side over a common denominator. The numerator becomes \\((1 + \varepsilon_n)^2 + 1\\):

$$
1 + \varepsilon_{n+1} = \frac{(1 + \varepsilon_n)^2 + 1}{2(1 + \varepsilon_n)}
$$

Expand \\((1 + \varepsilon_n)^2 = 1 + 2\varepsilon_n + \varepsilon_n^2\\):

$$
1 + \varepsilon_{n+1} = \frac{1 + 2\varepsilon_n + \varepsilon_n^2 + 1}{2(1 + \varepsilon_n)} = \frac{2 + 2\varepsilon_n + \varepsilon_n^2}{2(1 + \varepsilon_n)}
$$

Subtract 1 from both sides. On the right, 1 is the same as \\(\frac{2(1 + \varepsilon_n)}{2(1 + \varepsilon_n)} = \frac{2 + 2\varepsilon_n}{2(1 + \varepsilon_n)}\\):

$$
\varepsilon_{n+1} = \frac{2 + 2\varepsilon_n + \varepsilon_n^2}{2(1 + \varepsilon_n)} - \frac{2 + 2\varepsilon_n}{2(1 + \varepsilon_n)} = \frac{\varepsilon_n^2}{2(1 + \varepsilon_n)}
$$

So:

$$
\boxed{\;\varepsilon_{n+1} = \frac{\varepsilon_n^2}{2(1 + \varepsilon_n)}\;}
$$

This formula is **exact** — no approximations. It tells us three crucial things:

**1. After the first step, you always overestimate.** The numerator \\(\varepsilon_n^2\\) is non-negative (it's a square), and the denominator \\(2(1 + \varepsilon_n)\\) is positive as long as \\(\varepsilon_n > -1\\), which holds as long as our guess is positive. So \\(\varepsilon_{n+1} \ge 0\\) always. The first Babylonian step pushes us above \\(\sqrt{x}\\), and we stay there forever.

**2. The error roughly squares each step.** When \\(\varepsilon_n\\) is small, the denominator \\(2(1 + \varepsilon_n) \approx 2\\), so

$$
\varepsilon_{n+1} \approx \frac{\varepsilon_n^2}{2}
$$

If \\(\varepsilon_n = 0.01\\), then \\(\varepsilon_{n+1} \approx 0.00005\\). Squaring a small number makes it dramatically smaller. This is called **quadratic convergence**.

**3. Bits of accuracy roughly double per step.** Why? Take \\(-\log_2\\) of both sides of the approximate formula. \\(\log_2(\varepsilon^2/2) = 2\log_2(\varepsilon) - 1\\), so

$$
-\log_2(\varepsilon_{n+1}) \approx 2 \cdot (-\log_2(\varepsilon_n)) + 1
$$

In words: the number of correct bits doubles and gains one. Starting at 1 bit, you go \\(1 \to 3 \to 7 \to 15 \to 31 \to 63 \to 127\\). Six steps and you've crossed 128. (The actual numbers come out slightly better — we'll trace them shortly.)

This explains why exactly 6 iterations is right: starting from "around 1 bit of accuracy," 6 steps gets us past 128.

---

## Why the initial guess is half the bit length

Here's the Yul code for the initial guess again:

```solidity
z := shl(shr(1, sub(256, clz(x))), 1)
```

Reading the opcodes:

- `clz(x)` is the **c**ount of **l**eading **z**eros in \\(x\\)'s 256-bit representation.
- `sub(256, clz(x))` is therefore the bit length of \\(x\\) — call it \\(n+1\\) where \\(n = \lfloor\log_2(x)\rfloor\\).
- `shr(1, ...)` divides by 2 (right-shift by 1).
- `shl(..., 1)` shifts the value 1 left by that many positions, raising 2 to that power.

The whole expression computes \\(z_0 = 2^{\lfloor(n+1)/2\rfloor}\\).

**Why this is a good guess.** If \\(x\\) is around \\(2^n\\), then \\(\sqrt{x}\\) is around \\(2^{n/2}\\). The bit-length trick gives us a power of 2 that's within a factor of \\(\sqrt{2}\\) of the true answer.

Let's check the worst case. There are two cases depending on whether \\(n\\) is even or odd:

| If \\(n\\) is... | then \\(x\\) lies in... | \\(\sqrt{x}\\) lies in... | \\(z_0\\) is... | ratio \\(r_0 = z_0/\sqrt{x}\\) lies in... |
|---|---|---|---|---|
| even (\\(n = 2k\\)) | \\([2^{2k}, 2^{2k+1})\\) | \\([2^k, 2^k\sqrt{2})\\) | \\(2^k\\) | \\((1/\sqrt{2}, 1]\\) |
| odd (\\(n = 2k+1\\)) | \\([2^{2k+1}, 2^{2k+2})\\) | \\([2^k\sqrt{2}, 2^{k+1})\\) | \\(2^{k+1}\\) | \\((1, \sqrt{2}]\\) |

Combining both cases: \\(r_0 \in (1/\sqrt{2}, \sqrt{2}]\\). The farthest we can be from 1 is by a factor of \\(\sqrt{2}\\) in either direction, so the worst-case error is

$$
\lvert\varepsilon_0\rvert = \sqrt{2} - 1 \approx 0.4142
$$

How many bits of accuracy is that?

$$
-\log_2(0.4142) \approx 1.27
$$

We start with about 1.27 bits of accuracy. With quadratic convergence, 6 iterations will take us past 128. We'll verify this shortly.

---

## Why magic constants don't work for square roots

A natural optimization to try: "What if I multiply the initial guess by some clever constant \\(c\\) to tighten the worst case?"

If we use \\(z_0' = c \cdot 2^{\lfloor(n+1)/2\rfloor}\\) instead, the ratio range shifts from \\((1/\sqrt{2}, \sqrt{2}]\\) to \\((c/\sqrt{2}, c\sqrt{2}]\\). The question is: which value of \\(c\\) gives the smallest worst-case error after one Newton step?

Recall the symmetry: \\(g(r) = g(1/r)\\). The Newton map produces the same error for \\(r\\) and \\(1/r\\). So when looking at the worst-case point in our range, the *minimum possible worst-case* happens when the two endpoints of the range are reflections of each other across \\(r = 1\\) — meaning one endpoint equals \\(1/\\)(the other).

So we need:

$$
c\sqrt{2} = \frac{1}{c/\sqrt{2}}
$$

Solving:

$$
c\sqrt{2} \cdot \frac{c}{\sqrt{2}} = 1 \quad\Longrightarrow\quad c^2 = 1 \quad\Longrightarrow\quad c = 1
$$

**The best magic constant is 1. You shouldn't multiply by anything.**

To see why no other choice can do better, consider \\(c > 1\\). Then the high end \\(c\sqrt{2}\\) gets further from 1 (worse), while the low end \\(c/\sqrt{2}\\) gets closer to 1 (better). But the worst case is dominated by whichever endpoint is *further* from 1. Pushing one endpoint closer at the cost of pushing the other further can only hurt. Symmetric case for \\(c < 1\\).

This is purely a consequence of \\(g(r) = g(1/r)\\). Newton's iteration for square root is *symmetric in over- and under-estimates*. Any imbalance you introduce gets punished.

(Cube root, as we'll see at the end, has *no such symmetry* — and that's why cube root code has magic constants while square root code doesn't.)

---

## Why exactly 6 iterations?

Let's verify the iteration count by tracing the worst case. We start with \\(\varepsilon_0 = \sqrt{2} - 1\\). Apply the exact formula:

$$
\varepsilon_1 = \frac{(\sqrt{2} - 1)^2}{2(1 + (\sqrt{2} - 1))} = \frac{(\sqrt{2} - 1)^2}{2\sqrt{2}}
$$

Expand the numerator: \\((\sqrt{2} - 1)^2 = 2 - 2\sqrt{2} + 1 = 3 - 2\sqrt{2}\\). So:

$$
\varepsilon_1 = \frac{3 - 2\sqrt{2}}{2\sqrt{2}}
$$

Multiply top and bottom by \\(\sqrt{2}\\) to rationalize:

$$
\varepsilon_1 = \frac{(3 - 2\sqrt{2})\sqrt{2}}{2 \cdot 2} = \frac{3\sqrt{2} - 4}{4} \approx 0.0607
$$

This matches Solady's comment: *"This seed gives \\(\varepsilon_1 = 0.0607\\) after one Babylonian step for all inputs."*

Here is the full trace, applying \\(\varepsilon_{n+1} = \varepsilon_n^2/(2(1 + \varepsilon_n))\\) repeatedly:

| Step | \\(\varepsilon\\) | Bits |
|---|---|---|
| 0 | 0.4142 | 1.27 |
| 1 | 0.0607 | 4.04 |
| 2 | 0.00174 | 9.17 |
| 3 | \\(1.51 \times 10^{-6}\\) | 19.34 |
| 4 | \\(1.14 \times 10^{-12}\\) | 39.67 |
| 5 | \\(6.49 \times 10^{-25}\\) | 80.34 |
| 6 | \\(2.10 \times 10^{-49}\\) | **161.68** ✓ |

Six iterations get us to 161 bits of accuracy. This comfortably exceeds our 128-bit requirement.

- **5 iterations** would leave us at 80 bits — not enough.
- **7 iterations** would give us 323 bits — wasted gas.
- **6 iterations** is the smallest number that suffices.

The extra padding (from 128 to 161) is a safety margin that absorbs the small rounding effects of integer division, so the final correction step works cleanly.

---

## The subtle floor correction for perfect-square neighbors

The final line:

```solidity
z := sub(z, lt(div(x, z), z))
```

In words: if `x/z < z`, subtract 1 from \\(z\\). Since `x/z < z` is the same as `x < z²` (multiply both sides by \\(z\\)), this is the same as saying "if \\(z\\) overshot the true square root, fix it."

Why do we need this? Integer Babylonian iteration has a quirk: **when \\(x + 1\\) is a perfect square, the iteration oscillates between two adjacent integers forever.**

### Walking through the proof for x = 15

True \\(\sqrt{15} \approx 3.873\\). We want \\(\lfloor\sqrt{15}\rfloor = 3\\). Note that \\(15 + 1 = 16 = 4^2\\) — perfect square.

Starting from \\(z = 4\\) (which is \\(\lceil\sqrt{15}\rceil\\)):

- Step: \\(z = (4 + \lfloor 15/4 \rfloor)/2 = (4 + 3)/2 = 7/2 = 3\\) (integer division)

Now from \\(z = 3\\):

- Step: \\(z = (3 + \lfloor 15/3 \rfloor)/2 = (3 + 5)/2 = 8/2 = 4\\)

Now from \\(z = 4\\) again: same as before, drops to 3. The iteration ping-pongs between 3 and 4 forever.

**In general**, for any \\(x = n^2 - 1\\) (one less than a perfect square), the iteration cycles between \\(n - 1\\) and \\(n\\). We can prove it: starting from \\(z = n\\),

$$
\left\lfloor \frac{x}{n} \right\rfloor = \left\lfloor \frac{n^2 - 1}{n} \right\rfloor = \left\lfloor n - \frac{1}{n} \right\rfloor = n - 1
$$

So the next value is \\(\lfloor(n + (n-1))/2\rfloor = \lfloor(2n-1)/2\rfloor = n - 1\\). Starting from \\(z = n - 1\\),

$$
\left\lfloor \frac{x}{n - 1} \right\rfloor = \left\lfloor \frac{n^2 - 1}{n - 1} \right\rfloor = \left\lfloor n + 1 \right\rfloor = n + 1
$$

So the next value is \\(\lfloor((n-1) + (n+1))/2\rfloor = n\\). Back to \\(n\\), cycle confirmed.

After 6 iterations on a cycling input, we might land on \\(z = n\\), which is one above the floor. The correction line catches it: `x/z = (n²-1)/n = n - 1` (integer division), and `n - 1 < n = z`, so `lt(div(x,z), z) = 1`, and we subtract 1. Floor recovered.

For non-cycling inputs (the vast majority), the iteration converges exactly to \\(\lfloor\sqrt{x}\rfloor\\) with `x/z ≥ z`, so `lt(div(x,z), z) = 0` and the correction is a no-op.

---

## 10 facts in 8 lines

Every single line of this implementation is mathematically justified:

1. **Newton-Raphson \\(z_{n+1} = (z + x/z)/2\\) converges to \\(\sqrt{x}\\)** — equivalent to the Babylonian method.
2. **The error recurrence is independent of \\(x\\)** — substituting \\(z = r\sqrt{x}\\) cancels \\(x\\) out.
3. **The initial guess \\(z_0 = 2^{\lfloor(n+1)/2\rfloor}\\) starts with worst-case error \\(\sqrt{2} - 1 \approx 0.41\\)** — by case analysis on the parity of the bit length.
4. **The Newton map is symmetric: \\(g(r) = g(1/r)\\)** — verifiable by plugging in numbers.
5. **Because of this symmetry, the optimal magic constant is exactly 1** — no multiplier can improve the worst case.
6. **Quadratic convergence roughly doubles the bits of precision each step** — derived from \\(\varepsilon_{n+1} \approx \varepsilon_n^2 / 2\\).
7. **We only need 128 bits of accuracy** — because the maximum result fits in 128 bits.
8. **Six iterations reach 161 bits** — easily clearing the 128-bit hurdle, with a safety margin.
9. **Integer iteration cycles between two adjacent values when \\(x+1\\) is a perfect square** — proved by direct computation.
10. **The `lt(div(x,z), z)` check catches and corrects the cycle overshoot** — one subtraction is all that's needed.

---

## Coming next: cube root

What about cube roots? The Newton iteration is similar:

$$
z_{n+1} = \frac{2z + x/z^2}{3}
$$

But the \\(1/z^2\\) term breaks the symmetry we had for square roots. The cube-root error map does **not** satisfy \\(g(r) = g(1/r)\\) — and because of that, magic constants actually work.

In [Solady's `cbrt`](https://github.com/Vectorized/solady/blob/main/src/utils/clz/FixedPointMathLib.sol#L805-L831), you'll see the constant `0x90b5e5`. This packs three specific per-residue multipliers into one number, indexed by the bit length mod 3. Those multipliers tighten the initial guess enough that 5 iterations suffice instead of 7.

The pattern transfers cleanly: **the symmetry (or asymmetry) of the Newton map decides whether magic constants help.** For square roots, useless. For cube roots, essential. We'll derive the exact values of those multipliers in the sequel.