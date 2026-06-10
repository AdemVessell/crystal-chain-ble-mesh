# CRYSTAL_WALLETS_TOKENS.v0

Status: reference spec draft.

## Purpose

Define the minimal wallet and token payload carried by the CrystalChain BLE Mesh
reference ledger.

This document exists to preserve the original Crystal wallet/token direction
without turning the current research packet into a coin launch, investment
claim, or production settlement system.

## Design Rule

```text
Wallets and tokens are replayable signed ledger state.
Crystal localizes state divergence.
BLAKE3 and Ed25519 bind the data.
```

## Implemented Transaction Types

The current reference ledger supports three transaction types:

```text
create_wallet
mint
transfer
```

Each transaction is signed by an Ed25519 key, includes a nonce, and binds to the
current pre-state hash.

## Wallet Model

Wallets are keyed by `wallet_id`.

Each wallet stores:

```text
wallet_id
owner_public_key
wallet_role
```

Current wallet roles:

```text
user
founder
builder
gateway
watcher
```

Wallet creation rule:

```text
The owner public key must sign the create_wallet transaction.
```

The role is consensus-visible in the reference state. It is not merely display
metadata.

## Token Model

Tokens are keyed by `token_id`.

Each token stores:

```text
token_id
owner_wallet_id
token_class
```

Current token classes:

```text
mesh_credit
founder_marker
builder_marker
receipt
```

Mint rule:

```text
The signer must own the target wallet.
```

Transfer rule:

```text
The signer must own the source wallet.
The token must currently be assigned to the source wallet.
The destination wallet must exist.
```

## Founder And Builder Wallets

The current repo can represent founder and builder wallets as signed ledger
state:

```text
founder wallet:
  wallet_role = founder

builder wallet:
  wallet_role = builder
```

A founder wallet can mint a mesh-credit token into itself and transfer that token
to a builder wallet, subject to normal signature and ownership checks.

This is useful for testing the original product shape:

```text
offline local mesh
signed wallets
portable token/receipt state
fork-hold instead of silent merge
online checkpoints later
```

## Current Non-Claims

This V0 wallet/token layer does not currently claim:

```text
fungible balances
fixed supply
fees
staking
slashing
market value
financial settlement safety
custody safety
production wallet UX
public finality
Cloudflare checkpoint finality
real BLE transport
```

## Next Hardening Targets

```text
1. Decide whether mesh_credit should remain unique-token state or become
   fungible balance state.
2. Define mint authority policy for founder, builder, gateway, and watcher
   roles.
3. Add adversarial tests for duplicate tokens, replay, invalid role/class,
   unauthorized mint, unauthorized transfer, and forked double-spend attempts.
4. Define online checkpoint semantics before claiming finality.
5. Keep token language utility-oriented until economic policy and legal review
   exist.
```

