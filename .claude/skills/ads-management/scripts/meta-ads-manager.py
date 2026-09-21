#!/usr/bin/env python3
"""Meta/Facebook Ads API manager — create, modify, analyze campaigns via CLI.

Usage:
  python meta-ads-manager.py report [--preset last_30d] [--level campaign]
  python meta-ads-manager.py create-campaign --name NAME --objective OBJECTIVE
  python meta-ads-manager.py create-adset --campaign-id ID --name NAME --budget BUDGET --countries US
  python meta-ads-manager.py create-ad --adset-id ID --name NAME --page-id PID --image PATH --link URL --message TEXT
  python meta-ads-manager.py pause --id ID --type campaign|adset|ad
  python meta-ads-manager.py enable --id ID --type campaign|adset|ad
  python meta-ads-manager.py update-budget --adset-id ID --budget AMOUNT
  python meta-ads-manager.py billing [--account-id act_123,act_456] [--output json]
  python meta-ads-manager.py list-campaigns [--status ACTIVE|PAUSED]
  python meta-ads-manager.py export-campaign --campaign-id ID [--output FILE.json]

Requires: pip install facebook-business
Env vars: META_APP_ID, META_APP_SECRET, META_ACCESS_TOKEN, META_AD_ACCOUNT_ID
"""

import argparse
import json
import os
import sys
import time
from datetime import date
from pathlib import Path

# Add centralized resolver to path
_scripts_dir = Path(__file__).parent
_claude_scripts = _scripts_dir.parents[2] / 'scripts'
if _claude_scripts.exists():
    sys.path.insert(0, str(_claude_scripts))

try:
    from resolve_env import resolve_env
    _RESOLVER = True
except ImportError:
    _RESOLVER = False
    try:
        from dotenv import load_dotenv
    except ImportError:
        load_dotenv = None


def _resolve(var_name: str) -> str:
    """Resolve env var using centralized resolver or fallback."""
    if _RESOLVER:
        return resolve_env(var_name, skill='ads-management') or ""

    # Fallback: check process env first
    val = os.getenv(var_name)
    if val:
        return val

    # Fallback: load .env files, most specific first. override=False keeps
    # values already in the process env (e.g. a per-run META_ACCESS_TOKEN)
    # from being clobbered by a .env file loaded while resolving another var.
    if load_dotenv:
        skill_dir = _scripts_dir.parent
        skills_dir = skill_dir.parent
        claude_dir = skills_dir.parent
        for env_file in [_scripts_dir / '.env', skill_dir / '.env', skills_dir / '.env', claude_dir / '.env']:
            if env_file.exists():
                load_dotenv(env_file, override=False)
        val = os.getenv(var_name)
        if val:
            return val

    return ""


def init_api():
    """Initialize Meta Ads API from env vars."""
    try:
        from facebook_business.api import FacebookAdsApi
        from facebook_business.adobjects.adaccount import AdAccount
    except ImportError:
        print("ERROR: Install facebook-business package: pip install facebook-business")
        sys.exit(1)

    app_id = _resolve("META_APP_ID")
    app_secret = _resolve("META_APP_SECRET")
    access_token = _resolve("META_ACCESS_TOKEN")
    ad_account_id = _resolve("META_AD_ACCOUNT_ID")

    if not access_token:
        print("ERROR: META_ACCESS_TOKEN env var required.")
        print("Setup: export META_APP_ID, META_APP_SECRET, META_ACCESS_TOKEN, META_AD_ACCOUNT_ID")
        sys.exit(1)

    FacebookAdsApi.init(app_id, app_secret, access_token, api_version="v21.0")

    if not ad_account_id.startswith("act_"):
        ad_account_id = f"act_{ad_account_id}"
    return AdAccount(ad_account_id)


def _to_native(value):
    """Recursively convert facebook_business AbstractObject values to plain dict/list/str."""
    if hasattr(value, "export_all_data"):
        return _to_native(value.export_all_data())
    if isinstance(value, dict):
        return {k: _to_native(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_to_native(v) for v in value]
    return value


def cmd_report(account, args):
    """Get campaign/adset/ad performance insights."""
    from facebook_business.adobjects.adsinsights import AdsInsights

    fields = [
        AdsInsights.Field.campaign_name,
        AdsInsights.Field.campaign_id,
        AdsInsights.Field.impressions,
        AdsInsights.Field.clicks,
        AdsInsights.Field.spend,
        AdsInsights.Field.ctr,
        AdsInsights.Field.cpc,
        AdsInsights.Field.reach,
        AdsInsights.Field.frequency,
        AdsInsights.Field.actions,
        AdsInsights.Field.purchase_roas,
    ]
    params = {
        "date_preset": args.preset,
        "level": args.level,
    }

    insights = account.get_insights(fields=fields, params=params)
    results = []
    for row in insights:
        # Extract conversions from actions
        conversions = 0
        if row.get("actions"):
            for action in row["actions"]:
                if action["action_type"] in ("purchase", "lead", "complete_registration"):
                    conversions += float(action.get("value", 0))

        # Extract ROAS
        roas = 0
        if row.get("purchase_roas"):
            for r in row["purchase_roas"]:
                roas = float(r.get("value", 0))

        results.append({
            "campaign_id": row.get("campaign_id", ""),
            "campaign_name": row.get("campaign_name", ""),
            "impressions": int(row.get("impressions", 0)),
            "clicks": int(row.get("clicks", 0)),
            "spend": float(row.get("spend", 0)),
            "ctr": float(row.get("ctr", 0)),
            "cpc": float(row.get("cpc", 0)),
            "reach": int(row.get("reach", 0)),
            "frequency": float(row.get("frequency", 0)),
            "conversions": conversions,
            "roas": round(roas, 2),
        })

    print(json.dumps(results, indent=2))
    return results


def cmd_create_campaign(account, args):
    """Create a campaign."""
    from facebook_business.adobjects.campaign import Campaign

    # Map common objective names to API values
    objective_map = {
        "traffic": Campaign.Objective.outcome_traffic,
        "awareness": Campaign.Objective.outcome_awareness,
        "engagement": Campaign.Objective.outcome_engagement,
        "leads": Campaign.Objective.outcome_leads,
        "sales": Campaign.Objective.outcome_sales,
        "app_promotion": Campaign.Objective.outcome_app_promotion,
    }
    objective = objective_map.get(args.objective.lower(), args.objective)

    campaign = account.create_campaign(fields=[], params={
        Campaign.Field.name: args.name,
        Campaign.Field.objective: objective,
        Campaign.Field.status: Campaign.Status.paused,
        Campaign.Field.special_ad_categories: [],
        "is_adset_budget_sharing_enabled": False,
    })
    print(json.dumps({"status": "created", "campaign_id": campaign["id"], "name": args.name}))


def cmd_create_adset(account, args):
    """Create an ad set."""
    from facebook_business.adobjects.adset import AdSet

    targeting = {
        "geo_locations": {"countries": args.countries.split(",")},
    }
    if args.age_min:
        targeting["age_min"] = args.age_min
    if args.age_max:
        targeting["age_max"] = args.age_max

    adset = account.create_ad_set(fields=[], params={
        AdSet.Field.name: args.name,
        AdSet.Field.campaign_id: args.campaign_id,
        AdSet.Field.billing_event: AdSet.BillingEvent.impressions,
        AdSet.Field.optimization_goal: AdSet.OptimizationGoal.link_clicks,
        AdSet.Field.daily_budget: int(args.budget * 100),  # cents
        AdSet.Field.targeting: targeting,
        AdSet.Field.status: AdSet.Status.paused,
    })
    print(json.dumps({"status": "created", "adset_id": adset["id"], "name": args.name}))


def cmd_create_ad(account, args):
    """Create an ad with image creative."""
    from facebook_business.adobjects.adimage import AdImage
    from facebook_business.adobjects.adcreative import AdCreative
    from facebook_business.adobjects.ad import Ad

    # Upload image
    img = account.create_ad_image(fields=[], params={
        AdImage.Field.filename: args.image,
    })
    img_hash = img[AdImage.Field.hash]

    # Create creative
    creative = account.create_ad_creative(fields=[], params={
        AdCreative.Field.name: f"Creative-{args.name}",
        AdCreative.Field.object_story_spec: {
            "page_id": args.page_id,
            "link_data": {
                "image_hash": img_hash,
                "link": args.link,
                "message": args.message,
            },
        },
    })

    # Create ad
    ad = account.create_ad(fields=[], params={
        Ad.Field.name: args.name,
        Ad.Field.adset_id: args.adset_id,
        Ad.Field.creative: {"creative_id": creative["id"]},
        Ad.Field.status: Ad.Status.paused,
    })
    print(json.dumps({
        "status": "created",
        "ad_id": ad["id"],
        "creative_id": creative["id"],
        "image_hash": img_hash,
    }))


def cmd_set_status(account, args, status_value):
    """Pause or enable a campaign/adset/ad."""
    from facebook_business.adobjects.campaign import Campaign
    from facebook_business.adobjects.adset import AdSet
    from facebook_business.adobjects.ad import Ad

    obj_map = {
        "campaign": (Campaign, Campaign.Field.status),
        "adset": (AdSet, AdSet.Field.status),
        "ad": (Ad, Ad.Field.status),
    }
    cls, field = obj_map[args.type]
    obj = cls(args.id)
    obj.api_update(fields=[], params={field: status_value})
    print(json.dumps({"status": status_value, "id": args.id, "type": args.type}))


def cmd_update_budget(account, args):
    """Update ad set daily budget."""
    from facebook_business.adobjects.adset import AdSet

    adset = AdSet(args.adset_id)
    adset.api_update(fields=[], params={
        AdSet.Field.daily_budget: int(args.budget * 100),  # cents
    })
    print(json.dumps({"status": "updated", "adset_id": args.adset_id, "daily_budget_usd": args.budget}))


def cmd_export_campaign(account, args):
    """Export full campaign config (campaign, adsets, targeting, ads, creatives) as JSON."""
    from facebook_business.adobjects.campaign import Campaign
    from facebook_business.adobjects.adset import AdSet
    from facebook_business.adobjects.ad import Ad

    campaign_fields = [
        "id", "name", "objective", "status", "buying_type",
        "special_ad_categories", "bid_strategy", "daily_budget",
        "lifetime_budget", "is_adset_budget_sharing_enabled",
        "promoted_object", "start_time", "stop_time", "created_time",
    ]
    campaign = Campaign(args.campaign_id).api_get(fields=campaign_fields)

    adset_fields = [
        "id", "name", "status", "daily_budget", "lifetime_budget",
        "billing_event", "optimization_goal", "bid_strategy", "bid_amount",
        "targeting", "promoted_object", "attribution_spec",
        "destination_type", "is_dynamic_creative", "start_time", "end_time",
    ]
    ad_fields = ["id", "name", "status", "creative"]
    creative_fields = [
        "id", "name", "object_story_spec", "asset_feed_spec", "body", "title",
        "call_to_action_type", "effective_object_story_id", "image_url",
        "video_id", "url_tags", "instagram_permalink_url",
    ]

    from facebook_business.adobjects.adcreative import AdCreative

    adsets_out = []
    for adset in Campaign(args.campaign_id).get_ad_sets(fields=adset_fields):
        adset_dict = _to_native(dict(adset))
        ads_out = []
        for ad in AdSet(adset["id"]).get_ads(fields=ad_fields):
            ad_dict = _to_native(dict(ad))
            creative_ref = ad_dict.pop("creative", None)
            if creative_ref and creative_ref.get("id"):
                creative = AdCreative(creative_ref["id"]).api_get(fields=creative_fields)
                ad_dict["creative"] = _to_native(dict(creative))
            ads_out.append(ad_dict)
        adset_dict["ads"] = ads_out
        adsets_out.append(adset_dict)

    result = {"campaign": _to_native(dict(campaign)), "adsets": adsets_out}
    output_json = json.dumps(result, indent=2, ensure_ascii=False, default=str)

    if args.output:
        Path(args.output).write_text(output_json, encoding="utf-8")
        print(json.dumps({"status": "exported", "campaign_id": args.campaign_id, "output": args.output}))
    else:
        print(output_json)


RETIRED_FACEBOOK_POSITIONS = {"video_feeds"}


def cmd_clone_campaign(account, args):
    """Clone a campaign: same objective/budget/targeting/creative, new name, into this account."""
    from facebook_business.adobjects.campaign import Campaign
    from facebook_business.adobjects.adset import AdSet
    from facebook_business.adobjects.ad import Ad
    from facebook_business.adobjects.adcreative import AdCreative
    from facebook_business.exceptions import FacebookRequestError

    src_campaign_fields = [
        "objective", "buying_type", "bid_strategy", "daily_budget",
        "lifetime_budget", "special_ad_categories", "is_adset_budget_sharing_enabled",
    ]
    src = Campaign(args.source_campaign_id).api_get(fields=src_campaign_fields)

    campaign_params = {
        Campaign.Field.name: args.name,
        Campaign.Field.objective: src.get("objective"),
        Campaign.Field.buying_type: src.get("buying_type", "AUCTION"),
        Campaign.Field.special_ad_categories: _to_native(src.get("special_ad_categories", [])),
        "is_adset_budget_sharing_enabled": src.get("is_adset_budget_sharing_enabled", False),
        Campaign.Field.status: args.status,
    }
    if src.get("bid_strategy"):
        campaign_params[Campaign.Field.bid_strategy] = src["bid_strategy"]
    if src.get("daily_budget"):
        campaign_params[Campaign.Field.daily_budget] = src["daily_budget"]
    if src.get("lifetime_budget"):
        campaign_params[Campaign.Field.lifetime_budget] = src["lifetime_budget"]

    new_campaign = account.create_campaign(fields=[], params=campaign_params)
    new_campaign_id = new_campaign["id"]

    adset_fields = [
        "name", "billing_event", "optimization_goal", "bid_strategy", "bid_amount",
        "targeting", "promoted_object", "attribution_spec", "destination_type",
        "is_dynamic_creative", "daily_budget", "lifetime_budget",
    ]
    ad_fields = ["name", "status", "creative"]

    created_adsets = []
    created_ads = []
    for src_adset in Campaign(args.source_campaign_id).get_ad_sets(fields=adset_fields):
        targeting = _to_native(src_adset.get("targeting")) or {}
        # Placements retired by the API still linger on older ad sets and make
        # the create call fail; the API refuses them rather than ignoring them.
        if targeting.get("facebook_positions"):
            targeting["facebook_positions"] = [
                p for p in targeting["facebook_positions"] if p not in RETIRED_FACEBOOK_POSITIONS]
        # Instagram Explore home now requires the Explore placement alongside it.
        ig = targeting.get("instagram_positions") or []
        if "explore_home" in ig and "explore" not in ig:
            targeting["instagram_positions"] = ig + ["explore"]
        adset_params = {
            AdSet.Field.name: args.adset_name or src_adset.get("name"),
            AdSet.Field.campaign_id: new_campaign_id,
            AdSet.Field.billing_event: src_adset.get("billing_event"),
            AdSet.Field.optimization_goal: src_adset.get("optimization_goal"),
            AdSet.Field.targeting: targeting,
            AdSet.Field.status: args.status,
        }
        for field, key in [
            (AdSet.Field.promoted_object, "promoted_object"),
            (AdSet.Field.attribution_spec, "attribution_spec"),
            (AdSet.Field.destination_type, "destination_type"),
            (AdSet.Field.bid_strategy, "bid_strategy"),
            (AdSet.Field.bid_amount, "bid_amount"),
            (AdSet.Field.is_dynamic_creative, "is_dynamic_creative"),
        ]:
            if src_adset.get(key) is not None:
                adset_params[field] = _to_native(src_adset.get(key))
        if args.page_id and adset_params.get(AdSet.Field.promoted_object, {}).get("page_id"):
            adset_params[AdSet.Field.promoted_object]["page_id"] = args.page_id
        # Only set adset-level budget if the campaign has no CBO budget (Meta rejects both).
        if not campaign_params.get(Campaign.Field.daily_budget) and not campaign_params.get(Campaign.Field.lifetime_budget):
            if src_adset.get("daily_budget"):
                adset_params[AdSet.Field.daily_budget] = src_adset["daily_budget"]
            if src_adset.get("lifetime_budget"):
                adset_params[AdSet.Field.lifetime_budget] = src_adset["lifetime_budget"]

        try:
            new_adset = account.create_ad_set(fields=[], params=adset_params)
        except FacebookRequestError as exc:
            # Older ad sets can carry an attribution window Meta no longer allows
            # for their optimization goal (e.g. 7d click on CONVERSATIONS). Drop it
            # and let Meta apply the objective's current default.
            if exc.api_error_subcode() != 1885501 or AdSet.Field.attribution_spec not in adset_params:
                raise
            adset_params.pop(AdSet.Field.attribution_spec)
            new_adset = account.create_ad_set(fields=[], params=adset_params)
        new_adset_id = new_adset["id"]
        created_adsets.append(new_adset_id)

        if args.post_ids:
            # Replace the source ads with fresh ads built from the given Page
            # posts (e.g. swap a disapproved post for an approved one of the
            # same hook). Targeting/budget still come from the source campaign.
            post_ids = [p.strip() for p in args.post_ids.split(",") if p.strip()]
            ad_names = [n.strip() for n in (args.ad_names or "").split("|") if n.strip()]
            if ad_names and len(ad_names) != len(post_ids):
                print("ERROR: --ad-names must list one name per --post-ids entry, separated by '|'")
                sys.exit(1)
            for idx, post_id in enumerate(post_ids):
                new_creative = account.create_ad_creative(fields=[], params={"object_story_id": post_id})
                new_ad = account.create_ad(fields=[], params={
                    Ad.Field.name: ad_names[idx] if ad_names else post_id,
                    Ad.Field.adset_id: new_adset_id,
                    Ad.Field.creative: {"creative_id": new_creative["id"]},
                    Ad.Field.status: args.status,
                })
                created_ads.append({"ad_id": new_ad["id"], "creative_id": new_creative["id"], "source_post": post_id})
            continue

        for src_ad in AdSet(src_adset["id"]).get_ads(fields=ad_fields):
            creative_ref = src_ad.get("creative")
            if not creative_ref or not creative_ref.get("id"):
                continue
            src_creative = AdCreative(creative_ref["id"]).api_get(
                fields=["effective_object_story_id", "name", "object_story_spec",
                        "video_id", "body", "title", "call_to_action_type", "image_url"]
            )
            eos_id = src_creative.get("effective_object_story_id")
            # page_welcome_message (Messenger greeting) is set at creative-creation
            # time, not inherited from the post — must be copied explicitly.
            oss = _to_native(src_creative.get("object_story_spec")) or {}
            welcome_message = None
            for block in oss.values():
                if isinstance(block, dict) and block.get("page_welcome_message"):
                    welcome_message = block["page_welcome_message"]
                    break
            if args.page_id:
                # A different destination Page: an existing post (object_story_id)
                # belongs to the source Page and can't be reattached to another Page,
                # so rebuild the creative from scratch via object_story_spec — Meta
                # creates a fresh unpublished post under the target page_id instead.
                story_spec = {"page_id": args.page_id}
                if welcome_message:
                    story_spec["page_welcome_message"] = welcome_message
                video_id = src_creative.get("video_id")
                if video_id:
                    video_data = {
                        "video_id": video_id,
                        "call_to_action": {"type": src_creative.get("call_to_action_type") or "MESSAGE_PAGE"},
                    }
                    if src_creative.get("title"):
                        video_data["title"] = src_creative["title"]
                    if src_creative.get("body"):
                        video_data["message"] = src_creative["body"]
                    # video_data requires an explicit thumbnail (image_url/image_hash);
                    # the creative's own image_url is only populated for some creative
                    # types, so fall back to the video's own thumbnail list.
                    thumb_url = src_creative.get("image_url")
                    if not thumb_url:
                        from facebook_business.adobjects.advideo import AdVideo
                        thumbs = AdVideo(video_id).get_thumbnails(fields=["uri", "is_preferred"])
                        thumb_url = next((t["uri"] for t in thumbs if t.get("is_preferred")), None) \
                            or next((t["uri"] for t in thumbs), None)
                    if thumb_url:
                        video_data["image_url"] = thumb_url
                    story_spec["video_data"] = video_data
                else:
                    # Image-based creative: reuse the existing image (image_url
                    # accepted directly by link_data, no need to re-upload).
                    link_data = {"image_url": src_creative.get("image_url")}
                    if src_creative.get("title"):
                        link_data["name"] = src_creative["title"]
                    if src_creative.get("body"):
                        link_data["message"] = src_creative["body"]
                    story_spec["link_data"] = link_data
                new_creative = account.create_ad_creative(fields=[], params={
                    "name": src_creative.get("name"),
                    "object_story_spec": story_spec,
                })
                creative_id_to_use = new_creative["id"]
            elif eos_id:
                # Rebuild the creative in the destination account from the same
                # existing Page post — works across ad accounts (creative IDs don't).
                # NOTE: do not pass call_to_action_type here — the API rejects it
                # ("Application does not have the capability") on this app; the
                # existing post already carries its own CTA and the new creative
                # inherits it automatically.
                creative_create_params = {"object_story_id": eos_id}
                if welcome_message:
                    creative_create_params["page_welcome_message"] = welcome_message
                new_creative = account.create_ad_creative(fields=[], params=creative_create_params)
                creative_id_to_use = new_creative["id"]
            else:
                # No source post to rebuild from; only safe when staying in the same account.
                creative_id_to_use = creative_ref["id"]
            new_ad = account.create_ad(fields=[], params={
                Ad.Field.name: args.ad_name or src_ad.get("name"),
                Ad.Field.adset_id: new_adset_id,
                Ad.Field.creative: {"creative_id": creative_id_to_use},
                Ad.Field.status: args.status,
            })
            created_ads.append({"ad_id": new_ad["id"], "creative_id": creative_id_to_use, "source_post": eos_id})

    print(json.dumps({
        "status": "cloned",
        "source_campaign_id": args.source_campaign_id,
        "campaign_id": new_campaign_id,
        "adset_ids": created_adsets,
        "ads": created_ads,
    }, indent=2))


def cmd_list_campaigns(account, args):
    """List campaigns with optional status filter."""
    from facebook_business.adobjects.campaign import Campaign

    fields = [Campaign.Field.id, Campaign.Field.name, Campaign.Field.status,
              Campaign.Field.objective, Campaign.Field.daily_budget]
    params = {}
    if args.status:
        params["filtering"] = [{"field": "status", "operator": "EQUAL", "value": args.status.upper()}]

    campaigns = account.get_campaigns(fields=fields, params=params)
    results = []
    for c in campaigns:
        results.append({
            "id": c["id"],
            "name": c["name"],
            "status": c["status"],
            "objective": c.get("objective", ""),
            "daily_budget": float(c.get("daily_budget", 0)) / 100,
        })
    print(json.dumps(results, indent=2))


# Meta returns monetary account fields in the currency's minor unit. These currencies
# have no minor unit, so their raw values are already whole currency amounts.
ZERO_DECIMAL_CURRENCIES = {"CLP", "COP", "CRC", "HUF", "ISK", "JPY", "KRW", "PYG", "TWD", "VND"}

ACCOUNT_STATUS = {
    1: "ACTIVE", 2: "DISABLED", 3: "UNSETTLED", 7: "PENDING_RISK_REVIEW",
    8: "PENDING_SETTLEMENT", 9: "IN_GRACE_PERIOD", 100: "PENDING_CLOSURE",
    101: "CLOSED", 201: "ANY_ACTIVE", 202: "ANY_CLOSED",
}

DISABLE_REASON = {
    0: "NONE", 1: "ADS_INTEGRITY_POLICY", 2: "ADS_IP_REVIEW", 3: "RISK_PAYMENT",
    4: "GRAY_ACCOUNT_SHUT_DOWN", 5: "ADS_AFC_REVIEW", 6: "BUSINESS_INTEGRITY_RAR",
    7: "PERMANENT_CLOSE", 8: "UNUSED_RESELLER_ACCOUNT", 9: "UNUSED_ACCOUNT",
    10: "UMBRELLA_AD_ACCOUNT", 11: "BUSINESS_MANAGER_INTEGRITY_POLICY",
    12: "MISREPRESENTED_AD_ACCOUNT", 13: "AOAB_DESHARE_LEGAL_ENTITY",
    14: "CTX_THREAD_REVIEW", 15: "COMPROMISED_AD_ACCOUNT",
}


def _billing_account_ids(args):
    """Accounts to inspect: --account-id list, else META_AD_ACCOUNT_ID_N, else META_AD_ACCOUNT_ID."""
    raw = []
    if args.account_id:
        raw = [a.strip() for a in args.account_id.split(",") if a.strip()]
    else:
        i = 1
        while True:
            val = _resolve(f"META_AD_ACCOUNT_ID_{i}")
            if not val:
                break
            raw.append(val)
            i += 1
        single = _resolve("META_AD_ACCOUNT_ID")
        if single and single not in raw:
            raw.append(single)
    if not raw:
        print("ERROR: no ad account configured (META_AD_ACCOUNT_ID_1..N or META_AD_ACCOUNT_ID)")
        sys.exit(1)
    return [a if a.startswith("act_") else f"act_{a}" for a in raw]


def _money(raw, currency):
    """Convert a Meta minor-unit amount into whole currency units."""
    try:
        val = float(raw)
    except (TypeError, ValueError):
        return None
    return val if currency in ZERO_DECIMAL_CURRENCIES else val / 100


def _fmt_money(val, currency):
    return "-" if val is None else f"{val:,.0f} {currency}" if currency in ZERO_DECIMAL_CURRENCIES else f"{val:,.2f} {currency}"


# Vietnamese VAT on Meta ad invoices. Meta bills the pre-tax amount; the tax is added
# on the invoice, so the pre-tax threshold is what actually triggers a charge.
VAT_RATE = 0.10


def _billing_threshold(acc_id):
    """Pre-tax payment threshold for one account, in whole currency units.

    Meta does not expose this: the /adspaymentcycle edge that carried
    threshold_amount returns "nonexisting field" on v12-v21. It has to be read once
    from Ads Manager > Payment Settings and recorded as
    BILLING_THRESHOLD_<account digits> in .env — e.g. BILLING_THRESHOLD_1354368748313798.
    """
    raw = _resolve(f"BILLING_THRESHOLD_{acc_id.replace('act_', '')}")
    if not raw:
        return None
    try:
        return float(raw.replace(",", "").replace("_", "").strip())
    except ValueError:
        return None


def _billing_alert(row, threshold):
    """Classify payment health without a transaction feed.

    Meta charges the card when the pre-tax balance reaches the threshold and then
    resets the balance, so a balance still sitting above the threshold is the
    signal that the last charge did not go through.
    """
    if row["status"] in ("UNSETTLED", "PENDING_SETTLEMENT", "IN_GRACE_PERIOD")             or row["disable_reason"] == "RISK_PAYMENT":
        return "PAYMENT_ISSUE"
    balance = row["balance_due"]
    if threshold is None or balance is None:
        return "UNKNOWN (threshold not configured)"
    if balance > threshold:
        return "OVER_THRESHOLD (charge likely failed)"
    if balance >= threshold * 0.8:
        return "NEAR_THRESHOLD"
    return "OK"


def _month_spend(acc_id):
    """Spend so far in the calendar month containing today, in whole currency units.

    Insights returns spend in major units already (unlike the account-level
    `balance`/`amount_spent` fields, which are minor units) — do not rescale it.
    """
    from facebook_business.adobjects.adaccount import AdAccount
    rows = AdAccount(acc_id).get_insights(fields=["spend"], params={"date_preset": "this_month"})
    total = 0.0
    for r in rows:
        try:
            total += float(r.get("spend") or 0)
        except (TypeError, ValueError):
            pass
    return total


def _today_spend(acc_id):
    """Spend so far today, in whole currency units (insights already returns major units)."""
    from facebook_business.adobjects.adaccount import AdAccount
    rows = AdAccount(acc_id).get_insights(fields=["spend"], params={"date_preset": "today"})
    total = 0.0
    for r in rows:
        try:
            total += float(r.get("spend") or 0)
        except (TypeError, ValueError):
            pass
    return total


def _active_daily_budget(acc_id, currency):
    """Daily budget currently scheduled to spend, in whole currency units.

    A campaign-budget (CBO) campaign holds the budget itself and its ad sets carry
    none, so ad sets under a CBO campaign are skipped to avoid double counting.
    Lifetime-budget campaigns have no daily figure and are reported separately.
    """
    from facebook_business.adobjects.adaccount import AdAccount
    from facebook_business.adobjects.campaign import Campaign
    from facebook_business.adobjects.adset import AdSet

    account = AdAccount(acc_id)
    campaigns = account.get_campaigns(fields=[
        Campaign.Field.id, Campaign.Field.daily_budget, Campaign.Field.lifetime_budget,
        Campaign.Field.effective_status])
    cbo_daily = {}
    lifetime_only = 0
    active_campaigns = set()
    for c in campaigns:
        if c.get("effective_status") != "ACTIVE":
            continue
        active_campaigns.add(c["id"])
        if c.get("daily_budget"):
            cbo_daily[c["id"]] = _money(c["daily_budget"], currency)
        elif c.get("lifetime_budget"):
            lifetime_only += 1

    adsets = account.get_ad_sets(fields=[
        AdSet.Field.campaign_id, AdSet.Field.daily_budget, AdSet.Field.lifetime_budget,
        AdSet.Field.effective_status])
    adset_daily = 0.0
    for a in adsets:
        if a.get("effective_status") != "ACTIVE" or a.get("campaign_id") not in active_campaigns:
            continue
        if a.get("campaign_id") in cbo_daily:  # budget already counted at campaign level
            continue
        if a.get("daily_budget"):
            adset_daily += _money(a["daily_budget"], currency) or 0
        elif a.get("lifetime_budget"):
            lifetime_only += 1

    return {"daily_budget": adset_daily + sum(cbo_daily.values()),
            "lifetime_budget_entities": lifetime_only}


# Meta's ad account read is eventually consistent. For minutes after a charge settles,
# some replicas still serve the pre-charge `balance` while others serve the reset one.
# Observed 2026-08-26: two calls 2 seconds apart returned 17,121,178 and 11,148,278 VND
# for the same account, and Ads Manager confirmed the lower figure. A lagging replica has
# not applied the reset yet, so it always reads HIGH — the lowest sample is the settled
# state. Three cheap reads prevent a false "about to be charged" alarm and a top-up
# schedule built on debt that was already paid.
BALANCE_SAMPLES = 3
BALANCE_SAMPLE_DELAY_SECONDS = 1.0


def _stable_account_read(acc_id, fields):
    """Read one ad account several times and keep the sample with the lowest balance.

    Returns (data, seen): `seen` lists every distinct balance observed, so callers can
    tell the user the figure was still settling rather than presenting one silently.
    """
    from facebook_business.adobjects.adaccount import AdAccount

    def _bal(d):
        try:
            return float(d.get("balance"))
        except (TypeError, ValueError):
            return float("inf")

    samples = []
    for i in range(BALANCE_SAMPLES):
        if i:
            time.sleep(BALANCE_SAMPLE_DELAY_SECONDS)
        samples.append(_to_native(AdAccount(acc_id).api_get(fields=fields).export_all_data()))
    seen = sorted({_bal(d) for d in samples if _bal(d) != float("inf")})
    return min(samples, key=_bal), seen


def cmd_billing(account, args):
    """Report outstanding balance, spend cap, and account standing per ad account.

    The threshold comes from .env (see _billing_threshold), not from the API, and
    drives the payment-health alert: Meta exposes no transaction or invoice feed for
    card-billed accounts, so a balance above the threshold is the only available
    signal that a charge failed.
    """
    from facebook_business.adobjects.adaccount import AdAccount

    fields = ["name", "account_id", "account_status", "disable_reason", "currency", "balance",
              "amount_spent", "spend_cap", "is_prepay_account",
              "funding_source_details", "business_name"]

    results = []
    for acc_id in _billing_account_ids(args):
        row = {"account_id": acc_id}
        try:
            data, balance_samples = _stable_account_read(acc_id, fields)
        except Exception as exc:  # keep scanning the remaining accounts
            row["error"] = str(exc)
            results.append(row)
            continue
        currency = data.get("currency", "")
        row.update({
            "name": data.get("name", ""),
            "business": data.get("business_name", ""),
            "currency": currency,
            "status": ACCOUNT_STATUS.get(data.get("account_status"), data.get("account_status")),
            "disable_reason": DISABLE_REASON.get(data.get("disable_reason"), data.get("disable_reason")),
            "balance_due": _money(data.get("balance"), currency),
            "amount_spent": _money(data.get("amount_spent"), currency),
            "daily_budget_active": None,
            "spend_today": None,
            "balance_samples": balance_samples,
            "balance_unstable": len(balance_samples) > 1,
            "spend_this_month": None,
            "spend_this_month_period": date.today().strftime("%Y-%m"),
            "billing_threshold": None,
            "billing_threshold_with_vat": None,
            "threshold_pct": None,
            "spend_cap": _money(data.get("spend_cap"), currency),
            "prepaid": data.get("is_prepay_account"),
            "payment_method": (data.get("funding_source_details") or {}).get("display_string", ""),
        })
        try:
            budget = _active_daily_budget(acc_id, currency)
            row["daily_budget_active"] = budget["daily_budget"]
            row["lifetime_budget_entities"] = budget["lifetime_budget_entities"]
        except Exception as exc:
            row["daily_budget_error"] = str(exc)
        try:
            row["spend_today"] = _today_spend(acc_id)
        except Exception as exc:
            row["spend_today_error"] = str(exc)
        try:
            row["spend_this_month"] = _month_spend(acc_id)
        except Exception as exc:  # a failed insights call must not hide the billing fields
            row["spend_this_month_error"] = str(exc)
        threshold = _billing_threshold(acc_id)
        if threshold is not None:
            row["billing_threshold"] = threshold
            row["billing_threshold_with_vat"] = round(threshold * (1 + VAT_RATE), 2)
            row["threshold_pct"] = (round(row["balance_due"] / threshold * 100, 1)
                                    if row["balance_due"] is not None else None)
        if threshold and row["balance_due"] is not None and row["daily_budget_active"]:
            row["days_to_threshold"] = round(
                (threshold - row["balance_due"]) / row["daily_budget_active"], 1)
        else:
            row["days_to_threshold"] = None
        row["alert"] = _billing_alert(row, threshold)
        results.append(row)

    if args.output == "json":
        print(json.dumps(results, indent=2))
        return

    for r in results:
        print(f"=== {r['account_id']} {r.get('name', '')}")
        if r.get("error"):
            print(f"    ERROR: {r['error']}")
            print()
            continue
        cur = r["currency"]
        print(f"    Status          : {r['status']}   (disable_reason: {r['disable_reason']})")
        print(f"    Balance due     : {_fmt_money(r['balance_due'], cur)}")
        if r.get("balance_unstable"):
            spread = " / ".join(_fmt_money(b, cur) for b in r["balance_samples"])
            print(f"    !! still settling: reads disagreed ({spread}) — a charge is landing; "
                  f"lowest taken, re-check in a few minutes")
        if r.get("daily_budget_error"):
            print(f"    Daily budget    : ERROR - {r['daily_budget_error']}")
        else:
            extra = (f"   ({r['lifetime_budget_entities']} lifetime-budget entities not counted)"
                     if r.get("lifetime_budget_entities") else "")
            print(f"    Daily budget    : {_fmt_money(r['daily_budget_active'], cur)}{extra}")
        if r.get("spend_today_error"):
            print(f"    Spent today     : ERROR - {r['spend_today_error']}")
        else:
            print(f"    Spent today     : {_fmt_money(r['spend_today'], cur)}")
        if r.get("spend_this_month_error"):
            print(f"    Spent {r['spend_this_month_period']}  : ERROR - {r['spend_this_month_error']}")
        else:
            print(f"    Spent {r['spend_this_month_period']}  : {_fmt_money(r['spend_this_month'], cur)}")
        if r.get("billing_threshold") is None:
            print(f"    Bill threshold  : not configured — read it in Ads Manager > Payment Settings, "
                  f"then set BILLING_THRESHOLD_{r['account_id'].replace('act_', '')} in .env")
        else:
            print(f"    Bill threshold  : {_fmt_money(r['billing_threshold'], cur)} pre-tax   "
                  f"| {_fmt_money(r['billing_threshold_with_vat'], cur)} incl. VAT {VAT_RATE:.0%}")
            print(f"    Threshold used  : {r['threshold_pct']}%")
        print(f"    Spend cap       : {_fmt_money(r['spend_cap'], cur)}")
        print(f"    Payment method  : {r['payment_method'] or '-'}   (prepaid: {r['prepaid']})")
        if r.get("days_to_threshold") is not None:
            print(f"    Days to charge  : ~{r['days_to_threshold']} at current daily budget")
        print(f"    Alert           : {r['alert']}")
        print()


def main():
    # Account names are often non-ASCII; Windows consoles default to cp1252.
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except AttributeError:
        pass
    parser = argparse.ArgumentParser(description="Meta/Facebook Ads Manager CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    # report
    rpt = sub.add_parser("report", help="Campaign performance report")
    rpt.add_argument("--preset", default="last_30d", help="Date preset (last_7d, last_30d, this_month)")
    rpt.add_argument("--level", default="campaign", help="Report level (campaign, adset, ad)")

    # create-campaign
    cc = sub.add_parser("create-campaign", help="Create campaign")
    cc.add_argument("--name", required=True)
    cc.add_argument("--objective", required=True, help="traffic|awareness|engagement|leads|sales")

    # create-adset
    cas = sub.add_parser("create-adset", help="Create ad set")
    cas.add_argument("--campaign-id", required=True)
    cas.add_argument("--name", required=True)
    cas.add_argument("--budget", type=float, required=True, help="Daily budget in USD")
    cas.add_argument("--countries", default="US", help="Comma-separated country codes")
    cas.add_argument("--age-min", type=int, default=None)
    cas.add_argument("--age-max", type=int, default=None)

    # create-ad
    ca = sub.add_parser("create-ad", help="Create ad with image")
    ca.add_argument("--adset-id", required=True)
    ca.add_argument("--name", required=True)
    ca.add_argument("--page-id", required=True, help="Facebook Page ID")
    ca.add_argument("--image", required=True, help="Path to image file")
    ca.add_argument("--link", required=True, help="Destination URL")
    ca.add_argument("--message", required=True, help="Ad primary text")

    # pause
    p = sub.add_parser("pause", help="Pause campaign/adset/ad")
    p.add_argument("--id", required=True)
    p.add_argument("--type", required=True, choices=["campaign", "adset", "ad"])

    # enable
    e = sub.add_parser("enable", help="Enable campaign/adset/ad")
    e.add_argument("--id", required=True)
    e.add_argument("--type", required=True, choices=["campaign", "adset", "ad"])

    # update-budget
    ub = sub.add_parser("update-budget", help="Update ad set budget")
    ub.add_argument("--adset-id", required=True)
    ub.add_argument("--budget", type=float, required=True, help="Daily budget in USD")

    # billing
    bl = sub.add_parser("billing", help="Account debt/credit status, billing threshold, spend cap")
    bl.add_argument("--account-id", default=None, help="Comma-separated act_ IDs (default: all META_AD_ACCOUNT_ID_N in .env)")
    bl.add_argument("--output", default="text", choices=["text", "json"])

    # list-campaigns
    lc = sub.add_parser("list-campaigns", help="List campaigns")
    lc.add_argument("--status", default=None, help="Filter: ACTIVE, PAUSED")

    # export-campaign
    ec = sub.add_parser("export-campaign", help="Export full campaign config (adsets, targeting, ads, creatives)")
    ec.add_argument("--campaign-id", required=True)
    ec.add_argument("--output", default=None, help="Write JSON to file instead of stdout")

    # clone-campaign
    clc = sub.add_parser("clone-campaign", help="Clone a campaign (budget, targeting, creative) into this account under a new name")
    clc.add_argument("--source-campaign-id", required=True)
    clc.add_argument("--name", required=True, help="New campaign name")
    clc.add_argument("--adset-name", default=None, help="Override ad set name (default: same as source)")
    clc.add_argument("--ad-name", default=None, help="Override ad name (default: same as source)")
    clc.add_argument("--status", default="PAUSED", choices=["PAUSED", "ACTIVE"])
    clc.add_argument("--page-id", default=None, help="Override destination Facebook Page (rebuilds creative under this page instead of reusing the source Page's post)")
    clc.add_argument("--post-ids", default=None, help="Comma-separated Page post IDs (page_id_post_id); when set, source ads are not copied and one ad per post is created instead")
    clc.add_argument("--ad-names", default=None, help="'|'-separated ad names matching --post-ids order (default: post id)")

    args = parser.parse_args()
    account = init_api()

    if args.command == "report":
        cmd_report(account, args)
    elif args.command == "create-campaign":
        cmd_create_campaign(account, args)
    elif args.command == "create-adset":
        cmd_create_adset(account, args)
    elif args.command == "create-ad":
        cmd_create_ad(account, args)
    elif args.command == "pause":
        cmd_set_status(account, args, "PAUSED")
    elif args.command == "enable":
        cmd_set_status(account, args, "ACTIVE")
    elif args.command == "update-budget":
        cmd_update_budget(account, args)
    elif args.command == "billing":
        cmd_billing(account, args)
    elif args.command == "list-campaigns":
        cmd_list_campaigns(account, args)
    elif args.command == "export-campaign":
        cmd_export_campaign(account, args)
    elif args.command == "clone-campaign":
        cmd_clone_campaign(account, args)


if __name__ == "__main__":
    main()
