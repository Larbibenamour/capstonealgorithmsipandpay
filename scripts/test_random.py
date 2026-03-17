"""Randomized algorithm test - generates different data every run."""

import numpy as np
from datetime import datetime, timedelta
from src.scoring.schema import Order, OrderItem
from src.scoring.complexity import compute_order_complexity, compute_complexity_adjusted_cycle_time
from src.scoring.normalize import percentile_rank, compute_composite_score
from src.scoring.confidence import compute_overall_confidence, apply_shrinkage

# Use current time as seed for true randomness
seed = int(datetime.now().timestamp())
np.random.seed(seed)

print('=' * 70)
print('🎲 RANDOMIZED ALGORITHM TEST')
print('=' * 70)
print(f'Random seed: {seed} (different every run)')
print('Testing with 3 waiters, random orders/times/complexity')
print('-' * 70)

# Generate 3 random waiters
waiter_names = ['Waiter_A', 'Waiter_B', 'Waiter_C']
waiters_data = {}

print('\n📊 GENERATING RANDOM DATA...\n')

for waiter in waiter_names:
    # Random number of orders (between 10 and 50)
    n_orders = np.random.randint(10, 51)
    
    # Random performance profile
    base_efficiency = np.random.uniform(80, 150)  # sec/complexity_unit
    consistency = np.random.uniform(0.05, 0.35)  # dispersion
    
    # Generate random orders
    orders = []
    total_complexity = 0
    eff_raw_values = []
    
    for i in range(n_orders):
        # Random items (1-6 items per order)
        n_items = np.random.randint(1, 7)
        items = []
        order_complexity = 0
        
        for j in range(n_items):
            quantity = np.random.randint(1, 5)
            items.append(OrderItem(item_id=f"item_{j}", quantity=quantity))
            order_complexity += quantity
        
        total_complexity += order_complexity
        
        # Random cycle time based on complexity (with some noise)
        # Base: complexity * efficiency, plus random variation
        base_time = order_complexity * base_efficiency
        noise = np.random.normal(0, base_time * consistency)
        cycle_time = max(60, base_time + noise)  # Min 60 seconds
        
        eff_raw = cycle_time / order_complexity
        eff_raw_values.append(eff_raw)
        
        orders.append({
            'items': len(items),
            'complexity': order_complexity,
            'cycle_time': cycle_time
        })
    
    # Calculate stats
    median_eff = np.median(eff_raw_values)
    iqr_eff = np.percentile(eff_raw_values, 75) - np.percentile(eff_raw_values, 25)
    normalized_dispersion = iqr_eff / median_eff if median_eff > 0 else 0
    
    waiters_data[waiter] = {
        'n_orders': n_orders,
        'total_complexity': total_complexity,
        'median_eff_raw': median_eff,
        'eff_raw_values': eff_raw_values,
        'normalized_dispersion': normalized_dispersion,
        'orders': orders
    }
    
    print(f'{waiter}:')
    print(f'  Orders: {n_orders}')
    print(f'  Total complexity: {total_complexity:.0f} units')
    print(f'  Median efficiency: {median_eff:.1f} sec/unit')
    print(f'  Consistency (IQR): {normalized_dispersion:.2f}')

# Step 1: Normalize efficiency within the group
print('\n' + '=' * 70)
print('STEP 1: EFFICIENCY NORMALIZATION (Lower raw = Better score)')
print('=' * 70)

all_median_effs = [w['median_eff_raw'] for w in waiters_data.values()]

for waiter, data in waiters_data.items():
    # Percentile rank (0-100)
    percentile = percentile_rank(np.array(all_median_effs), data['median_eff_raw'])
    # Invert because lower efficiency raw is better
    eff_score = 100 - percentile
    data['eff_score'] = eff_score
    
    print(f'{waiter}: {data["median_eff_raw"]:.1f} sec/unit → Score: {eff_score:.1f}/100')

# Step 2: Throughput scoring
print('\n' + '=' * 70)
print('STEP 2: THROUGHPUT SCORING (More complexity/hour = Better)')
print('=' * 70)

# Assume 6 hour shift
SHIFT_HOURS = 6

all_throughputs = [w['total_complexity'] / SHIFT_HOURS for w in waiters_data.values()]
max_throughput = max(all_throughputs)

for waiter, data in waiters_data.items():
    throughput = data['total_complexity'] / SHIFT_HOURS
    # Normalize to 0-100
    thr_score = (throughput / max_throughput) * 100 if max_throughput > 0 else 50
    data['thr_score'] = thr_score
    
    print(f'{waiter}: {throughput:.1f} units/hour → Score: {thr_score:.1f}/100')

# Step 3: Consistency scoring
print('\n' + '=' * 70)
print('STEP 3: CONSISTENCY SCORING (Lower dispersion = Better)')
print('=' * 70)

all_dispersions = [w['normalized_dispersion'] for w in waiters_data.values()]

for waiter, data in waiters_data.items():
    percentile = percentile_rank(np.array(all_dispersions), data['normalized_dispersion'])
    # Invert because lower dispersion is better
    cons_score = 100 - percentile
    data['cons_score'] = cons_score
    
    print(f'{waiter}: Dispersion {data["normalized_dispersion"]:.2f} → Score: {cons_score:.1f}/100')

# Step 4: Composite score
print('\n' + '=' * 70)
print('STEP 4: COMPOSITE SCORE (50% Eff + 30% Thr + 20% Cons)')
print('=' * 70)

weights = {'efficiency': 0.50, 'throughput': 0.30, 'consistency': 0.20}

for waiter, data in waiters_data.items():
    composite = compute_composite_score(
        data['eff_score'],
        data['thr_score'],
        data['cons_score'],
        weights
    )
    data['composite'] = composite
    
    print(f'{waiter}: {composite:.1f}/100')
    print(f'  = {data["eff_score"]:.1f}×0.5 + {data["thr_score"]:.1f}×0.3 + {data["cons_score"]:.1f}×0.2')

# Step 5: Confidence and shrinkage
print('\n' + '=' * 70)
print('STEP 5: CONFIDENCE & SHRINKAGE')
print('=' * 70)

config = {'min_orders_for_confidence': 20}
baseline = np.median([w['composite'] for w in waiters_data.values()])
shrinkage_strength = 0.3

print(f'Baseline (median): {baseline:.1f}')
print(f'Shrinkage strength: {shrinkage_strength}\n')

for waiter, data in waiters_data.items():
    confidence = compute_overall_confidence(
        n_orders=data['n_orders'],
        total_complexity=data['total_complexity'],
        normalized_dispersion=data['normalized_dispersion'],
        config=config
    )
    data['confidence'] = confidence
    
    final_score = apply_shrinkage(
        data['composite'],
        baseline,
        confidence,
        shrinkage_strength
    )
    data['final_score'] = final_score
    
    change = final_score - data['composite']
    arrow = '↓' if change < -0.5 else '↑' if change > 0.5 else '≈'
    
    print(f'{waiter}:')
    print(f'  Confidence: {confidence:.2f} ({data["n_orders"]} orders)')
    print(f'  Raw score: {data["composite"]:.1f} → Final: {final_score:.1f} {arrow} {change:+.1f}')

# Final ranking
print('\n' + '=' * 70)
print('🏆 FINAL RANKING')
print('=' * 70)

sorted_waiters = sorted(waiters_data.items(), key=lambda x: x[1]['final_score'], reverse=True)

for rank, (waiter, data) in enumerate(sorted_waiters, 1):
    medal = '🥇' if rank == 1 else '🥈' if rank == 2 else '🥉'
    print(f'{medal} {waiter}: {data["final_score"]:.1f}/100')
    print(f'   ({data["n_orders"]} orders, {data["total_complexity"]:.0f} complexity units)')

print('\n' + '=' * 70)
print('✅ TEST COMPLETE')
print('=' * 70)
print(f'Run again for different random data (new seed: {int(datetime.now().timestamp())})')
