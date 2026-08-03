"""CLI for running AI Router benchmarks."""

from __future__ import annotations

import argparse
import asyncio
import json


def main():
    parser = argparse.ArgumentParser(description="AI Router Benchmark CLI")
    parser.add_argument("--model", default="gpt-4o-mini", help="Model to benchmark")
    parser.add_argument("--provider", default=None, help="Specific provider to test")
    parser.add_argument("--num-requests", type=int, default=10, help="Number of requests")
    parser.add_argument("--concurrency", type=int, default=5, help="Concurrent requests")
    parser.add_argument("--stream", action="store_true", help="Use streaming")
    parser.add_argument("--prompt", default="Say hello in one word", help="Test prompt")
    parser.add_argument("--output", default=None, help="Output file (JSON)")
    args = parser.parse_args()

    from benchmarks.runner import get_system_metrics, run_benchmark

    async def _run():
        print(
            f"Running benchmark: model={args.model}, num_requests={args.num_requests}, "
            f"concurrency={args.concurrency}, stream={args.stream}"
        )

        result = await run_benchmark(
            model=args.model,
            provider=args.provider,
            num_requests=args.num_requests,
            concurrency=args.concurrency,
            stream=args.stream,
            prompt=args.prompt,
        )

        data = result.to_dict()

        print("\n--- Benchmark Results ---")
        print(f"Duration: {data['duration_seconds']}s")
        print(f"Avg Latency: {data['average_latency_ms']}ms")
        print(f"P95: {data['p95_latency_ms']}ms")
        print(f"P99: {data['p99_latency_ms']}ms")
        print(f"Throughput: {data['throughput_reqs_per_sec']} req/s")
        print(f"Success Rate: {data['success_rate'] * 100:.1f}%")
        print(f"Errors: {data['errors']}")
        print(f"Fallback Count: {data['fallback_count']}")

        if not args.stream:
            metrics = await get_system_metrics()
            print("\nSystem Metrics:")
            print(f"  Cache Hit Ratio: {metrics['cache_hit_ratio'] * 100:.1f}%")
            print(f"  Total Requests: {metrics['total_requests']}")
            print(f"  Success Rate: {metrics['success_rate'] * 100:.1f}%")

        if args.output:
            with open(args.output, "w") as f:
                json.dump(data, f, indent=2)
            print(f"\nResults saved to {args.output}")

        return data

    return asyncio.run(_run())


if __name__ == "__main__":
    main()
