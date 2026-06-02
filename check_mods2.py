"""Deeper mod activity analysis"""
import pandas as pd
from datetime import datetime

comments_df = pd.read_csv('data/r_Hedera/comments.csv')
comments_df['created_utc'] = pd.to_datetime(comments_df['created_utc'], errors='coerce')
mask = (comments_df['created_utc'] >= '2026-05-05') & (comments_df['created_utc'] <= '2026-05-11 23:59:59')
comments_p = comments_df[mask]

print("=" * 80)
print("DETAILED MOD INTERVENTION ANALYSIS — May 5-11")
print("=" * 80)

# Hedera-ModTeam comments (official mod actions)
print()
print("HEDERA-MODTEAM ACTIONS:")
print("-" * 80)
modteam = comments_p[comments_p['author'].fillna('') == 'Hedera-ModTeam']
for _, c in modteam.iterrows():
    print("Post: " + str(c.get('post_title', ''))[:60])
    print("Action: " + str(c['body'])[:200].replace('\n', ' '))
    print("Date: " + str(c['created_utc']))
    print()

# AutoModerator actions
print("AUTOMODERATOR ACTIONS:")
print("-" * 80)
automod = comments_p[comments_p['author'].fillna('') == 'AutoModerator']
for _, c in automod.iterrows():
    print("Post: " + str(c.get('post_title', ''))[:60])
    print("Action: " + str(c['body'])[:200].replace('\n', ' '))
    print("Date: " + str(c['created_utc']))
    print()

# Count removed comments per post
print("REMOVED COMMENTS BY POST:")
print("-" * 80)
removed = comments_p[comments_p['body'].fillna('').isin(['[removed]', '[deleted]'])]
post_groups = removed.groupby('post_title').size().sort_values(ascending=False)
for title, count in post_groups.items():
    print("  " + str(count) + " removed — " + str(title)[:60])

# Summary stats
print()
print("=" * 80)
print("MOD SUMMARY FOR REPORT:")
print("=" * 80)
print("Hedera-ModTeam interventions: " + str(len(modteam)))
print("AutoModerator removals: " + str(len(automod)))
print("Total removed/deleted comments: " + str(len(removed)))
print("Posts with removed comments: " + str(len(post_groups)))

# Posts where mods took action
affected_posts = set()
for _, c in modteam.iterrows():
    affected_posts.add(str(c.get('post_title', ''))[:60])
for _, c in automod.iterrows():
    affected_posts.add(str(c.get('post_title', ''))[:60])
print("Posts with direct mod intervention: " + str(len(affected_posts)))
for p in affected_posts:
    print("  -> " + p)
