"""Drive the real hub-sdk against tools/mock_hub_server.py and check the reconstructed protocol + suspected defects."""
import os, sys, tempfile, time
os.environ["ULTRALYTICS_HUB_API"] = os.environ.get("ULTRALYTICS_HUB_API", "http://127.0.0.1:8787")
from hub_sdk import HUBClient  # noqa: E402
from hub_sdk.modules.teams import TeamList  # noqa: E402
from hub_sdk.modules.users import Users  # noqa: E402

KEY = "test0000000000000000000000000000000000000000"[:42]
results = {}
c = HUBClient({"api_key": KEY}); results["auth_ok"] = c.authenticated
bad = HUBClient({"api_key": "wrong"}); results["bad_key_rejected"] = not bad.authenticated
m = c.model("MODEL123"); results["model_config_reshaped"] = m.data.get("config", {}).get("imageSize") == 640
m.upload_metrics({"0": '{"metrics/mAP50(B)": 0.1}'})
w = tempfile.NamedTemporaryFile(suffix=".pt", delete=False); w.write(b"\0" * 2048); w.close()
m.upload_model(epoch=1, weights=w.name, is_best=True)
m.upload_model(epoch=3, weights=w.name, map=0.42, final=True)
m.start_heartbeat(interval=1); time.sleep(2.5)
results["heartbeat_agent_id"] = m.hub_client.agent_id
u = Users("u1", c.get_auth_header()); results["users_data_empty_bug"] = u.data == {}
tl = TeamList(page_size=10, public=None, headers=c.get_auth_header())
results["teamlist_hits_datasets_endpoint_bug"] = tl.base_url.endswith("/v1/datasets")
results["teamlist_headers_passed_as_public_bug"] = tl.public == c.get_auth_header() and tl.headers is None
m.stop_heartbeat()
for k, v in results.items(): print(f"{k}: {v}")
sys.exit(0)
