#!/usr/bin/env bash
set -euo pipefail

# ========== 基本参数 ==========
BIN=${BIN:-bggdd}
CHAIN_ID=${CHAIN_ID:-bgg-local-1}
DENOM=${DENOM:-stake}

H1=${H1:-$HOME/.bggd-node1}
H2=${H2:-$HOME/.bggd-node2}

NODE1_MONIKER=${NODE1_MONIKER:-attacker-node}
NODE2_MONIKER=${NODE2_MONIKER:-honest-node}

KEYRING=${KEYRING:-test}

# 最小修改：
# 攻击者初始 stake 极小，诚实方初始 stake 较高。
VAL1_STAKE=${VAL1_STAKE:-1stake}
VAL2_STAKE=${VAL2_STAKE:-100000000stake}

GENESIS_BALANCE=${GENESIS_BALANCE:-1000000000000stake}

echo "BIN=$BIN"
echo "CHAIN_ID=$CHAIN_ID"
echo "DENOM=$DENOM"
echo "H1=$H1"
echo "H2=$H2"

mkdir -p experiments
mkdir -p experiments/logs

# ========== 停止旧进程 ==========
echo "[1/12] stop old nodes if any"
pkill -f "$BIN start --home $H1" || true
pkill -f "$BIN start --home $H2" || true
sleep 1

# ========== 清理旧链数据 ==========
echo "[2/12] remove old homes"
rm -rf "$H1" "$H2"

# ========== 初始化两个节点 ==========
echo "[3/12] init node homes"
$BIN init "$NODE1_MONIKER" --chain-id "$CHAIN_ID" --home "$H1"
$BIN init "$NODE2_MONIKER" --chain-id "$CHAIN_ID" --home "$H2"

# ========== 创建 key ==========
echo "[4/12] create keys"

$BIN keys add val1 --keyring-backend "$KEYRING" --home "$H1"
$BIN keys add attacker_pool --keyring-backend "$KEYRING" --home "$H1"
$BIN keys add honest_pool --keyring-backend "$KEYRING" --home "$H1"
$BIN keys add reserve_pool --keyring-backend "$KEYRING" --home "$H1"

$BIN keys add val2 --keyring-backend "$KEYRING" --home "$H2"

VAL1_ADDR=$($BIN keys show val1 -a --keyring-backend "$KEYRING" --home "$H1")
VAL2_ADDR=$($BIN keys show val2 -a --keyring-backend "$KEYRING" --home "$H2")
ATTACKER_POOL_ADDR=$($BIN keys show attacker_pool -a --keyring-backend "$KEYRING" --home "$H1")
HONEST_POOL_ADDR=$($BIN keys show honest_pool -a --keyring-backend "$KEYRING" --home "$H1")
RESERVE_POOL_ADDR=$($BIN keys show reserve_pool -a --keyring-backend "$KEYRING" --home "$H1")

VAL1_VALOPER=$($BIN keys show val1 --bech val -a --keyring-backend "$KEYRING" --home "$H1")
VAL2_VALOPER=$($BIN keys show val2 --bech val -a --keyring-backend "$KEYRING" --home "$H2")

echo "VAL1_ADDR=$VAL1_ADDR"
echo "VAL2_ADDR=$VAL2_ADDR"
echo "ATTACKER_POOL_ADDR=$ATTACKER_POOL_ADDR"
echo "HONEST_POOL_ADDR=$HONEST_POOL_ADDR"
echo "RESERVE_POOL_ADDR=$RESERVE_POOL_ADDR"
echo "VAL1_VALOPER=$VAL1_VALOPER"
echo "VAL2_VALOPER=$VAL2_VALOPER"

# ========== 写入 genesis account ==========
echo "[5/12] add genesis accounts"

$BIN genesis add-genesis-account "$VAL1_ADDR" "$GENESIS_BALANCE" --home "$H1"
$BIN genesis add-genesis-account "$VAL2_ADDR" "$GENESIS_BALANCE" --home "$H1"
$BIN genesis add-genesis-account "$ATTACKER_POOL_ADDR" "$GENESIS_BALANCE" --home "$H1"
$BIN genesis add-genesis-account "$HONEST_POOL_ADDR" "$GENESIS_BALANCE" --home "$H1"
$BIN genesis add-genesis-account "$RESERVE_POOL_ADDR" "$GENESIS_BALANCE" --home "$H1"

# 把 node1 的 genesis 复制给 node2，用同一个 genesis 生成 gentx。
cp "$H1/config/genesis.json" "$H2/config/genesis.json"

# ========== 生成两个 genesis validator ==========
echo "[6/12] gentx for two validators"

$BIN genesis gentx val1 "$VAL1_STAKE" \
  --chain-id "$CHAIN_ID" \
  --keyring-backend "$KEYRING" \
  --home "$H1"

$BIN genesis gentx val2 "$VAL2_STAKE" \
  --chain-id "$CHAIN_ID" \
  --keyring-backend "$KEYRING" \
  --home "$H2"

mkdir -p "$H1/config/gentx"
cp "$H2/config/gentx/"*.json "$H1/config/gentx/"

# ========== 收集 gentx ==========
echo "[7/12] collect gentxs"
$BIN genesis collect-gentxs --home "$H1"
$BIN genesis validate-genesis --home "$H1"

# 最终 genesis 同步到 node2。
cp "$H1/config/genesis.json" "$H2/config/genesis.json"

# ========== 配置不同端口 ==========
echo "[8/12] configure node ports"

# node1 使用默认:
# p2p 26656, rpc 26657, abci 26658

# node2 改端口:
# p2p 26666, rpc 26667, abci 26668
sed -i.bak 's/tcp:\/\/127.0.0.1:26657/tcp:\/\/127.0.0.1:26667/g' "$H2/config/config.toml"
sed -i.bak 's/tcp:\/\/0.0.0.0:26656/tcp:\/\/0.0.0.0:26666/g' "$H2/config/config.toml"
sed -i.bak 's/tcp:\/\/127.0.0.1:26658/tcp:\/\/127.0.0.1:26668/g' "$H2/config/config.toml"

# app.toml 端口避免冲突，不同 Cosmos SDK 版本字段可能不同，失败不影响主流程。
sed -i.bak 's/address = "tcp:\/\/0.0.0.0:1317"/address = "tcp:\/\/0.0.0.0:1318"/g' "$H2/config/app.toml" || true
sed -i.bak 's/address = "0.0.0.0:9090"/address = "0.0.0.0:9091"/g' "$H2/config/app.toml" || true
sed -i.bak 's/address = "0.0.0.0:9091"/address = "0.0.0.0:9092"/g' "$H2/config/app.toml" || true

# 设置 minimum-gas-prices。
sed -i.bak "s/minimum-gas-prices = \"\"/minimum-gas-prices = \"0${DENOM}\"/g" "$H1/config/app.toml" || true
sed -i.bak "s/minimum-gas-prices = \"\"/minimum-gas-prices = \"0${DENOM}\"/g" "$H2/config/app.toml" || true

# ========== 配置 peer ==========
echo "[9/12] configure persistent peers"

NODE1_ID=$($BIN tendermint show-node-id --home "$H1")
NODE2_ID=$($BIN tendermint show-node-id --home "$H2")

NODE1_PEER="${NODE1_ID}@127.0.0.1:26656"
NODE2_PEER="${NODE2_ID}@127.0.0.1:26666"

echo "NODE1_PEER=$NODE1_PEER"
echo "NODE2_PEER=$NODE2_PEER"

sed -i.bak "s/persistent_peers = \"\"/persistent_peers = \"$NODE2_PEER\"/g" "$H1/config/config.toml"
sed -i.bak "s/persistent_peers = \"\"/persistent_peers = \"$NODE1_PEER\"/g" "$H2/config/config.toml"

# ========== 输出实验 config ==========
echo "[10/12] write experiments/config.yaml"

cat > experiments/config.yaml <<CFG
run_id: cosmos_bgg_low_intensity_500blocks_001
seed: 42

binary: ${BIN}
chain_id: ${CHAIN_ID}
node_rpc: http://127.0.0.1:26657
home: ${H1}
keyring_backend: ${KEYRING}

denom: ${DENOM}
gas: auto
gas_adjustment: "1.5"
fees: 5000${DENOM}

attacker_account: attacker_pool
honest_account: honest_pool
reserve_account: reserve_pool

attacker_valoper: ${VAL1_VALOPER}
honest_valoper: ${VAL2_VALOPER}

# 低强度参数：
# 降低攻击者和诚实方的 Poisson 到达强度，便于观察防御动作是否及时生效。
lambda_A: 0.3
lambda_H: 0.2
stake_unit: 1000000

# action 仍然使用 rho_A 触发。
theta_action: 0.3333333333

# T_old / T_math 在 Python 中使用绝对 voting power 阈值判断。
theta_old: 0.5
theta_post: 0.5

# 本地实验配置的基准 voting power。
# 不是实时 total_power，也不是主网 validator 总数。
M_power: 200000001

# reserve delegation。
reserve_units: 20

# runtime。
step_sleep_seconds: 3
max_steps: 1000

# reserve effective 后只继续观察 500 个块。
post_defense_blocks: 500

results_dir: experiments/results/cosmos_bgg_low_intensity_500blocks_001
CFG

# ========== 保存地址 ==========
echo "[11/12] write experiments/addresses.env"

cat > experiments/addresses.env <<ADDR
export BIN=${BIN}
export CHAIN_ID=${CHAIN_ID}
export DENOM=${DENOM}
export H1=${H1}
export H2=${H2}
export KEYRING=${KEYRING}

export VAL1_ADDR=${VAL1_ADDR}
export VAL2_ADDR=${VAL2_ADDR}
export ATTACKER_POOL_ADDR=${ATTACKER_POOL_ADDR}
export HONEST_POOL_ADDR=${HONEST_POOL_ADDR}
export RESERVE_POOL_ADDR=${RESERVE_POOL_ADDR}

export VAL1_VALOPER=${VAL1_VALOPER}
export VAL2_VALOPER=${VAL2_VALOPER}

export NODE1_ID=${NODE1_ID}
export NODE2_ID=${NODE2_ID}
export NODE1_PEER=${NODE1_PEER}
export NODE2_PEER=${NODE2_PEER}
ADDR

# ========== 启动节点 ==========
echo "[12/12] start nodes"

nohup $BIN start --home "$H1" > experiments/logs/node1.log 2>&1 &
echo $! > experiments/logs/node1.pid

nohup $BIN start --home "$H2" > experiments/logs/node2.log 2>&1 &
echo $! > experiments/logs/node2.pid

echo "Waiting for blocks..."
sleep 8

echo "Latest block:"
curl -s http://127.0.0.1:26657/status | jq '.result.sync_info.latest_block_height' || true

echo ""
echo "Done."
echo "Config written to: experiments/config.yaml"
echo "Addresses written to: experiments/addresses.env"
echo "Logs:"
echo "  experiments/logs/node1.log"
echo "  experiments/logs/node2.log"