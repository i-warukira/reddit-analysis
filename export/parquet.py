"""
Parquet Export Module - For DuckDB/Warehouse integration
Export scraped data to Parquet format for analytics tools.
"""
import pandas as pd
from pathlib import Path
from datetime import datetime

def export_to_parquet(subreddit, output_dir=None, prefix="r"):
    """
    Export subreddit data to Parquet format.
    
    Args:
        subreddit: Subreddit name
        output_dir: Output directory (default: data/parquet)
        prefix: "r" for subreddit, "u" for user
    
    Returns:
        Dictionary with paths to exported files
    """
    try:
        import pyarrow
    except ImportError:
        raise ImportError("pyarrow required for Parquet export. Run: pip install pyarrow")
    
    # Setup paths
    data_dir = Path(f"data/{prefix}_{subreddit}")
    output_path = Path(output_dir) if output_dir else Path("data/parquet")
    output_path.mkdir(parents=True, exist_ok=True)
    
    if not data_dir.exists():
        print(f"❌ No data found for {prefix}/{subreddit}")
        return {}
    
    exported = {}
    timestamp = datetime.now().strftime("%Y%m%d")
    
    # Export posts
    posts_csv = data_dir / "posts.csv"
    if posts_csv.exists():
        print(f"📦 Converting posts to Parquet...")
        df = pd.read_csv(posts_csv)
        
        # Convert datetime columns
        if 'created_utc' in df.columns:
            df['created_utc'] = pd.to_datetime(df['created_utc'], errors='coerce')
        
        # Optimize dtypes
        for col in ['score', 'num_comments', 'num_crossposts', 'total_awards']:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0).astype('int32')
        
        for col in ['is_nsfw', 'is_spoiler', 'has_media', 'media_downloaded']:
            if col in df.columns:
                df[col] = df[col].astype(bool)
        
        output_file = output_path / f"{subreddit}_posts_{timestamp}.parquet"
        df.to_parquet(output_file, engine="pyarrow", compression="snappy")
        
        size_mb = output_file.stat().st_size / (1024 * 1024)
        print(f"   ✅ {output_file.name} ({len(df)} rows, {size_mb:.2f} MB)")
        exported['posts'] = str(output_file)
    
    # Export comments
    comments_csv = data_dir / "comments.csv"
    if comments_csv.exists():
        print(f"📦 Converting comments to Parquet...")
        df = pd.read_csv(comments_csv)
        
        if 'created_utc' in df.columns:
            df['created_utc'] = pd.to_datetime(df['created_utc'], errors='coerce')
        
        if 'score' in df.columns:
            df['score'] = pd.to_numeric(df['score'], errors='coerce').fillna(0).astype('int32')
        
        output_file = output_path / f"{subreddit}_comments_{timestamp}.parquet"
        df.to_parquet(output_file, engine="pyarrow", compression="snappy")
        
        size_mb = output_file.stat().st_size / (1024 * 1024)
        print(f"   ✅ {output_file.name} ({len(df)} rows, {size_mb:.2f} MB)")
        exported['comments'] = str(output_file)
    
    print(f"\n✅ Export complete! Files saved to: {output_path}")
    print(f"   💡 Query with DuckDB: duckdb.query(\"SELECT * FROM '{exported.get('posts', '')}' LIMIT 10\")")
    
    return exported


def export_database_to_parquet(output_dir=None):
    """
    Export entire SQLite database to Parquet files.
    
    Args:
        output_dir: Output directory
    
    Returns:
        Dictionary with paths to exported files
    """
    try:
        import pyarrow
    except ImportError:
        raise ImportError("pyarrow required. Run: pip install pyarrow")
    
    from export.database import get_connection
    
    output_path = Path(output_dir) if output_dir else Path("data/parquet")
    output_path.mkdir(parents=True, exist_ok=True)
    
    conn = get_connection()
    exported = {}
    timestamp = datetime.now().strftime("%Y%m%d")
    
    tables = ['posts', 'comments', 'job_history']
    
    for table in tables:
        try:
            print(f"📦 Exporting {table}...")
            df = pd.read_sql(f"SELECT * FROM {table}", conn)
            
            if len(df) > 0:
                output_file = output_path / f"db_{table}_{timestamp}.parquet"
                df.to_parquet(output_file, engine="pyarrow", compression="snappy")
                
                size_mb = output_file.stat().st_size / (1024 * 1024)
                print(f"   ✅ {output_file.name} ({len(df)} rows, {size_mb:.2f} MB)")
                exported[table] = str(output_file)
            else:
                print(f"   ⏭️ {table} is empty, skipping")
        except Exception as e:
            print(f"   ❌ Failed to export {table}: {e}")
    
    conn.close()
    return exported


def list_parquet_files(directory="data/parquet"):
    """List all Parquet files in directory."""
    parquet_dir = Path(directory)
    
    if not parquet_dir.exists():
        print(f"📁 No Parquet directory found at {directory}")
        return []
    
    files = list(parquet_dir.glob("*.parquet"))
    
    print(f"\n📁 Parquet Files in {directory}:")
    print("-" * 60)
    
    for f in files:
        size_mb = f.stat().st_size / (1024 * 1024)
        mtime = datetime.fromtimestamp(f.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
        print(f"   {f.name:<40} {size_mb:>6.2f} MB  {mtime}")
    
    print("-" * 60)
    print(f"Total: {len(files)} files")
    
    return [str(f) for f in files]


# CLI for testing
if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Parquet Export")
    parser.add_argument("subreddit", nargs='?', help="Subreddit to export")
    parser.add_argument("--user", action="store_true", help="Is a user profile")
    parser.add_argument("--output", type=str, help="Output directory")
    parser.add_argument("--database", action="store_true", help="Export entire database")
    parser.add_argument("--list", action="store_true", help="List Parquet files")
    
    args = parser.parse_args()
    
    if args.list:
        list_parquet_files()
    elif args.database:
        export_database_to_parquet(args.output)
    elif args.subreddit:
        prefix = "u" if args.user else "r"
        export_to_parquet(args.subreddit, args.output, prefix)
    else:
        parser.print_help()
