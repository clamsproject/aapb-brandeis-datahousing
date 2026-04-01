# Developer Notes

[Index](notes.md) 

## The GUIDS

There is a method `get_aapb_guid_from()` in `clams_utils.aapb.guidhandler` that extracts the guid from the location. It does almost the same as the following when given a location.

```python
import pathlib
location_example = "file://cpb-aacip-507-n29p26qt59.video"
guid = pathlib.Path(loc).stem}
```

I tested this on 200 randomly sampled MMIF files from the MMIF Storage server, making sure that each pipeline is represented. The one exception over these test data is in locations like 

```
file:////aapb-collaboration-21/cpb-aacip-507-4746q1t25k-transcript.txt
```

where `get_aapb_guid_from()` does not include "-transcript" in the guid.

As far as what the guids are used for, they are used for two actions: storing a MMIF file and retrieving MMIF files (or lists of MMIF files). 

**Storing a MMIF file**

The MMIF file being stored has no name associated with it, it is just a serialized MMIF object that is handed in to the API as the POST data via the -d option. The GUID is generated from the MMIF object, basically by taking a substring of the location of the first document in the documents list. This is probably really the only way that makes sense. We could consider making the POST data a dictionary of some name for the index and the MMIF object:

```json
{ 
  "identifier": "<some-identifier>",
  "mmif": "<some serialized MMIF object>"
}
```

Other meta data could be added if needed, one main drawback is that this requires the user to manage all the identifiers. I am not a great fan of this at the moment.

**Retrieving MMIF files**

There are two parameters, a pipeline and an identifier (the GUID in the AAPB case). The pipeline is required, at the moment there is no functionality to retrieve all MMIF files for all pipelines as long as the MMIF files match the GUID (which does appear useful). If there is an identifier then it will be used to seek a MMIF file in the storage that matches the pipeline and the identifier.

**How to generalize**

I assume that we will be able to straightforwardly get an identifier from any MMIF file. With that in place, the changes to make this work beyond AAPB files are fairly simple, we just need a generic method to create an identifier, which could be to just take the stem of the path to the location. And when we set up a server it should be told whether it is a generic MMIF server or an AAPB MMIF server (with other types to be added if needed).

**Other remarks**

The above is all based on having a server API accessed via a simple URL. To this day I do not really understand how the storage server is accessed from a CLAMS app and I do not know whether complications can arise from that.

On identifier/guid creation from the MMIF file. The way we do that now for AAPB relies on taking the first document and extract the identifier from the file path. It would probably be better to generalize that a bit to generating an identifier from all primary source documents. The most general way would be some kind of concatenation of all identifier-like substrings from all document locations. This is somewhat ugly and may make retrieval a bit of a pain because you cannot just rely on a simple identifier and the pipeline. At the moment we sort of assume there is a simple single identifier, and we could add an explicit requirement formalizing this stating that there should be a simple procedure that maps each location to the same identifier, in which case we can simply take the identifier from the first document. The current code makes this possible because if there are two primary documents the locations would be like `file://cpb-aacip-507-n29p26qt59.video` and `file://cpb-aacip-507-n29p26qt59-transcript.txt` and since the result of processing is alway one MMIF file it can be simply `cpb-aacip-507-n29p26qt59.mmif` in the storage.
