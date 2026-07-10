# Minimal Cosmos BGG Local Experiment

## 1. Overview

This repository contains a minimal Cosmos SDK / CometBFT local BGG-style experiment. Only two files are included:

- `start_bgg_2node_min.sh`
- `run_bgg_cosmos_min.py`

The shell script starts a two-node local Cosmos / CometBFT network and writes:

```text
experiments/config.yaml
```

The Python script acts as an external controller. It reads `config.yaml`, samples Poisson arrivals, submits attacker / honest / reserve delegations, queries validator voting power, and writes experiment results.

In this experiment, attacker and honest resources are interpreted as bonded / delegated voting power, not validator count.

This local experiment only shows that the mechanism is executable and observable under local settings. It does not prove any mainnet-level security claim.

---

## 2. Repository Structure

```text
bgg-cosmos-experiment/
├── start_bgg_2node_min.sh
└── run_bgg_cosmos_min.py
```

Runtime files are generated automatically:

```text
experiments/
├── config.yaml
├── addresses.env
├── logs/
└── results/
    └── cosmos_bgg_low_intensity_500blocks_001/
        ├── events.jsonl
        └── summary.json
```

Each run generates event logs and a summary containing:

- Parameters
- Network config
- All `T_*` metrics
- Final voting power
- Action status
- Threshold status
- Error counts
- Result paths

---

## 3. Install System Dependencies

```bash
sudo apt update
sudo apt install -y \
  build-essential \
  curl \
  wget \
  git \
  jq \
  tar \
  python3 \
  python3-pip \
  python3-venv
```

---

## 4. Install Go

Example Go installation:

```bash
cd /tmp
GO_VERSION=1.23.6

wget -O go${GO_VERSION}.linux-amd64.tar.gz \
  https://go.dev/dl/go${GO_VERSION}.linux-amd64.tar.gz

sudo rm -rf /usr/local/go
sudo tar -C /usr/local -xzf go${GO_VERSION}.linux-amd64.tar.gz

echo 'export PATH=$PATH:/usr/local/go/bin:$HOME/go/bin' >> ~/.bashrc
source ~/.bashrc

go version
```

Official Go install reference:

```text
https://go.dev/doc/install
```

---

## 5. Install Ignite CLI

```bash
curl -L "https://get.ignite.com/cli!" | bash

if [ -f ./ignite ]; then
  sudo mv ./ignite /usr/local/bin/ignite
fi

ignite version
```

Official Ignite install reference:

```text
https://docs.ignite.com/welcome/install
```

---

## 6. Build the Cosmos Chain Binary

If you already have the chain source:

```bash
cd ~/bgg-cosmos/bggd
ignite chain build
```

If you need a fresh minimal chain:

```bash
mkdir -p ~/bgg-cosmos
cd ~/bgg-cosmos

ignite scaffold chain bggd --address-prefix bgg

cd bggd
ignite chain build
```

Check the binary:

```bash
which bggdd
bggdd version
```

If `bggdd` is not found:

```bash
export PATH="$PATH:$HOME/go/bin"

which bggdd
bggdd version
```

`bggdd` is the full node program.

- Cosmos SDK handles accounts, balances, staking, and delegation.
- CometBFT handles P2P, block production, voting, commit, and validator voting power.

---

## 7. Clone This Repository

```bash
cd ~/bgg-cosmos

git clone https://github.com/YOUR_NAME/YOUR_REPO.git bgg-cosmos-experiment

cd bgg-cosmos-experiment
```

---

## 8. Prepare Python Environment

```bash
python3 -m venv .venv

source .venv/bin/activate

pip install --upgrade pip
pip install numpy pyyaml requests
```

---

## 9. Start the Local Network

```bash
chmod +x start_bgg_2node_min.sh

./start_bgg_2node_min.sh
```

The script will:

- Initialize two local nodes
- Create local accounts
- Create two validators
- Collect gentx files
- Validate genesis
- Configure ports and peers
- Write `experiments/config.yaml`
- Start the network

The network uses the following default ports for `node1`:

- CometBFT RPC: `26657`
- P2P: `26656`

If a node reports a minimum gas price error, use:

```bash
--minimum-gas-prices 0.001stake
```

Or modify `app.toml`.

---

## 10. Check Network Status

Check latest block height:

```bash
curl -s http://127.0.0.1:26657/status \
  | jq '.result.sync_info.latest_block_height'
```

Watch block production:

```bash
watch -n 2 "curl -s http://127.0.0.1:26657/status | jq '.result.sync_info.latest_block_height'"
```

CometBFT status includes:

- `latest_block_height`
- `catching_up`
- `validator_info.voting_power`

Check validators:

```bash
source experiments/addresses.env

bggdd query staking validators \
  --node http://127.0.0.1:26657 \
  -o json \
  | jq -r '.validators[] | "\(.operator_address) \(.tokens) \(.status) \(.description.moniker)"'
```

---

## 11. Run the Experiment

```bash
source .venv/bin/activate

python3 run_bgg_cosmos_min.py
```

The Python controller records JSONL events, such as:

- `NETWORK_STARTED`
- `POISSON_SAMPLED`
- `ACTION_TRIGGERED`
- `RESERVE_ALL_EFFECTIVE`
- `OLD_THRESHOLD_REACHED`
- `MATH_THRESHOLD_REACHED`
- `RUN_FINISHED`
- `ERROR`

The experiment uses external state files instead of an `x/bgg` module.

---

## 12. View Results

Show summary:

```bash
jq . experiments/results/cosmos_bgg_low_intensity_500blocks_001/summary.json
```

Show latest events:

```bash
tail -n 30 experiments/results/cosmos_bgg_low_intensity_500blocks_001/events.jsonl
```

Follow events live:

```bash
tail -f experiments/results/cosmos_bgg_low_intensity_500blocks_001/events.jsonl
```

---

## 13. Stop the Network

```bash
kill "$(cat experiments/logs/node1.pid)" "$(cat experiments/logs/node2.pid)" || true
```

Force stop if needed:

```bash
pkill -f "bggdd start" || true
```

---

## 14. Notes

- `M_power` is a configured BGG-style local experiment parameter.
- `M_power` is not the real-time validator set size.
- `M_power` is not an Ethereum mainnet security threshold.
- `T_old` means the attacker reaches the original configured threshold.
- `T_math` means the attacker reaches the post-defense mathematical threshold.
- Short-window block-share warnings should not be treated as confirmed majority attacks.
- This experiment should be described as a local executable and observable BGG-style defense experiment.
- This experiment should not be described as proof that a real 51% attack can be defended.
