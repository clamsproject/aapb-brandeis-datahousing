# Developer Notes

[Index](notes.md) 


## MMIF downloads

When you do not give it a pipeline it crashes. Changed that to make it a bit more robust.


#### Zero-guid scenario

Scenario when all we hand in is a pipeline specification. The response has the pipeline path and all the matched MMIF files"

```bash
curl -X POST 127.0.0.1:8001/storeapi/download \
    -H 'Content-Type: "application/json"' \
    -d '{"pipeline": {"NON_EXISTING_APP/v2.20": {}}}'
```
```json
{
  "filenames": [],
  "pipeline": "/Users/Shared/aapb/storage-test/NON_EXISTING_APP/v2.20/84319c756bde16522347d3df188e73d9"
}
```

> TODO:<br/>Don't return the full pipeline, just the part from the local root (that is, strip the STORAGE_DIR prefix)

Or with an existing path with stuff in it:

```bash
curl -X POST 127.0.0.1:8001/storeapi/download \
    -H 'Content-Type: "application/json"' \
    -d '{"pipeline": {"chyron-detection/v1.0": {}}}'
```
 
```json
{
  "filenames": [
    "cpb-aacip-507-cf9j38m509",
    "cpb-aacip-507-bz6154fc44",
    "cpb-aacip-525-028pc2v94s",
    "cpb-aacip-507-pr7mp4wf25",
    "cpb-aacip-507-6w96689725"
  ],
  "pipeline": "/Users/Shared/aapb/storage-test/chyron-detection/v1.0/d41d8cd98f00b204e9800998ecf8427e"
}
```


### Single-guid scenario

Scenario where we hand in a pipeline specification and an AAPB GUID. Response is single MMIF file or a warning message.

```json
curl -X POST 127.0.0.1:8001/storeapi/download \
    -H 'Content-Type: "application/json"' \
    -d '
    {
        "pipeline": { "chyron-detection/v1.0": {} },
        "guid": "cpb-aacip-507-bz6154fc44"
    }'
```

This is implemented, but it returns an error if the GUID does not exist. If no error it returns a text string represeting a MMIF object. You save it to file and then can nicely print it with "cat fname | jq".

With a non-existing MMIF file we get an error:

```bash
curl -X POST 127.0.0.1:8001/storeapi/download \
    -H 'Content-Type: "application/json"' \
    -d '{ "pipeline": { "chyron-detection/v1.0": {} }, "guid": "NO-SUCH-GUID" }'
```
```json
{
  "error": "Did not find: NO-SUCH-GUID"
}
```


### Multi-guid scenario

In this case we get a pipeline and a list of GUIDs, and the response is a dictionary of MMIF files or error messages.

```json
curl -X POST 127.0.0.1:8001/storeapi/download \
    -H 'Content-Type: "application/json"' \
    -d '{"pipeline": {
    		"chyron-detection/v1.0": {}},
    		"guid":["NO_SUCH_GUID", "cpb-aacip-525-028pc2v94s"]}'
```

```json
{
  "NON-EXISTING-GUID": {
    "error": "Did not find: NON-EXISTING-GUID"
  },
  "cpb-aacip-525-028pc2v94s": {
    "documents": [],
    "metadata": {},
    "views": []
  }  
}
```

New version:

```json
curl -X POST 127.0.0.1:8001/storeapi/download \
    -H 'Content-Type: "application/zip"' \
    --output multi-guid-response.zip \
    -d '
    {
        "pipeline": { "whisper-wrapper/v3": {"modelSize": "tiny"} },
        "guid": ["cpb-aacip-507-7659c6sk7z", "cpb-aacip-507-zk55d8pd1h"]
    }'
```


### Some things to check

I HAVE NOT CHECKED WHAT HAPPENS WHEN A GUID DOES NOT EXIST

I HAVE NOT CHECKED THE REWINDER

> "in addition to the simple file retrieval, we can dynamically "rewind" MMIFs if there's any decedent MMIF exists."
