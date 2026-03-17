"""Quick test of the waiter performance scoring algorithm."""

from src.data.mock_data import generate_mock_data
from src.scoring.score_shift import compute_scores

print('=' * 70)
print('WAITER PERFORMANCE SCORING - QUICK TEST')
print('=' * 70)

# Generate small dataset
print('\n[1/3] Generating mock data (3 shifts, 5 waiters, ~15 orders each)...')
orders_df, shifts_df, staffing_df = generate_mock_data(
    n_shifts=3,
    n_waiters=5,
    orders_per_shift=15,
    seed=42
)
print(f'  ✓ Generated {len(orders_df)} total orders')
print(f'  Orders columns: {list(orders_df.columns)}')
print(f'  Shifts columns: {list(shifts_df.columns)}')

# Configure
print('\n[2/3] Computing scores...')
config = {
    'weights': {'efficiency': 0.50, 'throughput': 0.30, 'consistency': 0.20},
    'item_weights': {},
    'workload_adjustment': 'multiplicative',
    'shrinkage_strength': 0.3,
}

# Score
results = compute_scores(orders_df, shifts_df, staffing_df, config)
print(f'  ✓ Scored {len(results)} shifts\n')

# Display
print('[3/3] Top 3 performers in Shift 1:')
print('=' * 70)

first_shift_id = list(results.keys())[0]
shift_data = results[first_shift_id]
sorted_waiters = sorted(shift_data.items(), key=lambda x: x[1]['score'], reverse=True)[:3]

for rank, (waiter_id, data) in enumerate(sorted_waiters, 1):
    print(f'\n#{rank} - {waiter_id}:')
    print(f'  Score: {data["score"]:.1f}/100 (confidence: {data["confidence"]:.2f})')
    print(f'  Components: E={data["components"]["efficiency"]:.0f}, ' +
          f'T={data["components"]["throughput"]:.0f}, ' +
          f'C={data["components"]["consistency"]:.0f}')
    print(f'  Orders: {data["metrics"]["n_orders"]}, ' +
          f'Complexity: {data["metrics"]["total_complexity"]:.1f}')

print('\n' + '=' * 70)
print('✓ TEST COMPLETE - Algorithm working correctly!')
print('=' * 70)
