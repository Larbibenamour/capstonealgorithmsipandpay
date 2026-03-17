"""Visual demonstration of algorithm fairness and scoring."""

import numpy as np
from datetime import datetime, timedelta
from src.scoring.schema import Order, OrderItem
from src.scoring.complexity import compute_order_complexity
from src.scoring.normalize import percentile_rank, compute_composite_score
from src.scoring.confidence import compute_overall_confidence, apply_shrinkage

print('=' * 70)
print('ALGORITHM DEMONSTRATION: FAIRNESS IN ACTION')
print('=' * 70)

print('\n📊 SCENARIO: Friday Night Shift at Downtown Venue')
print('   Time: 8pm - 2am, 5 waiters working')
print('-' * 70)

# Simulate 5 waiters with different performance profiles
waiters = {
    'Alice': {'orders': 45, 'avg_eff_raw': 90, 'consistency': 0.15, 'profile': 'Fast & Consistent'},
    'Bob':   {'orders': 50, 'avg_eff_raw': 105, 'consistency': 0.30, 'profile': 'Fast but Erratic'},
    'Carol': {'orders': 40, 'avg_eff_raw': 120, 'consistency': 0.12, 'profile': 'Steady & Reliable'},
    'Dave':  {'orders': 8,  'avg_eff_raw': 85, 'consistency': 0.10, 'profile': 'New (Low Sample)'},
    'Eve':   {'orders': 35, 'avg_eff_raw': 140, 'consistency': 0.20, 'profile': 'Slower Pace'},
}

print('\n1️⃣  STEP 1: Raw Performance Metrics')
print('-' * 70)
print(f'{"Waiter":<10} {"Profile":<22} {"Orders":<8} {"Efficiency":<12} {"Consistency"}')
print(f'{"":10} {"":22} {"":8} {"(sec/unit)":<12}')
for name, data in waiters.items():
    print(f'{name:<10} {data["profile"]:<22} {data["orders"]:<8} {data["avg_eff_raw"]:<12.0f} {data["consistency"]:.2f}')

# Collect all efficiency values for percentile ranking
all_eff_values = np.array([w['avg_eff_raw'] for w in waiters.values()])

print('\n2️⃣  STEP 2: Within-Shift Normalization (Percentile Ranking)')
print('-' * 70)
print('Converting raw metrics to 0-100 scores relative to peers...')

results = {}
for name, data in waiters.items():
    # Efficiency: lower is better, so invert
    eff_percentile = percentile_rank(all_eff_values, data['avg_eff_raw'])
    eff_score = 100 - eff_percentile  # Invert: fast waiter gets high score
    
    # Throughput (simulated): more orders = higher throughput
    throughput_score = (data['orders'] / 50) * 100  # Normalized to max 50 orders
    
    # Consistency: lower dispersion is better
    consistency_score = (1 - data['consistency']) * 100  # Invert
    
    results[name] = {
        'eff_score': eff_score,
        'thr_score': throughput_score,
        'cons_score': consistency_score,
        'orders': data['orders']
    }

print(f'{"Waiter":<10} {"Efficiency":<12} {"Throughput":<12} {"Consistency"}')
for name, res in results.items():
    print(f'{name:<10} {res["eff_score"]:<12.1f} {res["thr_score"]:<12.1f} {res["cons_score"]:.1f}')

print('\n3️⃣  STEP 3: Composite Scoring (Weighted Combination)')
print('-' * 70)
print('Weights: 50% Efficiency + 30% Throughput + 20% Consistency')

weights = {'efficiency': 0.50, 'throughput': 0.30, 'consistency': 0.20}

for name, res in results.items():
    composite = compute_composite_score(
        res['eff_score'], 
        res['thr_score'], 
        res['cons_score'], 
        weights
    )
    results[name]['composite'] = composite

print(f'{"Waiter":<10} {"Raw Composite Score":<20}')
for name, res in results.items():
    print(f'{name:<10} {res["composite"]:<20.1f}')

print('\n4️⃣  STEP 4: Confidence Scoring')
print('-' * 70)
print('Confidence increases with: more orders, lower variance')

config = {'min_orders_for_confidence': 20}

for name, res in results.items():
    confidence = compute_overall_confidence(
        n_orders=waiters[name]['orders'],
        total_complexity=waiters[name]['orders'] * 5,  # Assume avg 5 complexity/order
        normalized_dispersion=waiters[name]['consistency'],
        config=config
    )
    results[name]['confidence'] = confidence

print(f'{"Waiter":<10} {"Orders":<8} {"Confidence":<12}')
for name, res in results.items():
    print(f'{name:<10} {res["orders"]:<8} {res["confidence"]:<12.2f}')

print('\n5️⃣  STEP 5: Shrinkage (Protecting Against Small Samples)')
print('-' * 70)
print('Low-confidence scores are adjusted toward group median...')

baseline = np.median([res['composite'] for res in results.values()])
shrinkage_strength = 0.3

print(f'Group baseline (median): {baseline:.1f}')
print(f'Shrinkage strength: {shrinkage_strength}\n')

for name, res in results.items():
    final_score = apply_shrinkage(
        res['composite'], 
        baseline, 
        res['confidence'], 
        shrinkage_strength
    )
    results[name]['final_score'] = final_score

print(f'{"Waiter":<10} {"Raw":<10} {"Confidence":<12} {"Final Score":<12} {"Change"}')
for name, res in results.items():
    change = res['final_score'] - res['composite']
    arrow = '↓' if change < -0.5 else '↑' if change > 0.5 else '≈'
    print(f'{name:<10} {res["composite"]:<10.1f} {res["confidence"]:<12.2f} {res["final_score"]:<12.1f} {arrow} {change:+.1f}')

print('\n🏆 FINAL RANKINGS')
print('=' * 70)

sorted_waiters = sorted(results.items(), key=lambda x: x[1]['final_score'], reverse=True)

for rank, (name, res) in enumerate(sorted_waiters, 1):
    medal = '🥇' if rank == 1 else '🥈' if rank == 2 else '🥉' if rank == 3 else f'{rank}.'
    profile = waiters[name]['profile']
    print(f'{medal} {name:<10} Score: {res["final_score"]:.1f}/100 ({profile})')

print('\n' + '=' * 70)
print('KEY INSIGHTS:')
print('=' * 70)
print('✓ Dave has excellent raw metrics BUT low confidence (only 8 orders)')
print('  → Shrinkage prevents over-rewarding a potentially lucky small sample')
print('')
print('✓ Alice combines good speed + high consistency + high volume')
print('  → Rewarded for well-rounded, reliable performance')
print('')
print('✓ Bob is fast but inconsistent')
print('  → Consistency penalty prevents rewarding erratic service')
print('')
print('✓ All scores are RELATIVE to peers in same shift')
print('  → Fair comparison under identical conditions (kitchen, rush, etc.)')
print('=' * 70)
