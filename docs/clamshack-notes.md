# ClamShack developer notes

Most of the following notes are relevant to Brandeis developers only.


### Assets

The ClamShack code is based on the MMIF Storage code where recreating a source potentially introduces non-determinism of workflow results. We are considering an approach where we can have multiple sources for a GUID. For the ClamShack this is not a problem though because MMIF sources will never be recreated.

Todo:

- Make sure that the mime type is properly derived from the path, at the moment it expects there to be a path part that matches `text` or `video`.
- Determine whether we allow additonal files to be added. If not, initialization of a ClamShack should require an asset list. If we do allow later additions, then we should at least make sure that the top-level directory path is the same. And we should also perhaps deal with the fact that two runs on the default batch may involve different files.
- Also to be determined is whether we really want to allow batches or just define the ClamShack as something that is created for a batch.


### Workflows and ClamsApps

Todo:

- For the registration step we admonish users to not forget the scheme and blabber about the differences between curl and register. Just update the register command so it prepends the scheme if it is not there.
- You could run SWT on the MMIF sources, and while this job runs create a second job that runs the captioner on the output of SWT. This won't work because the captioner will then not apply to all assets because they won't be there. For example, if the captioner starts when SWT has not created output yet then the captioner will immediately exit. Maybe add some checks that make sure this cannot happen.


### MMIF storage

It would be useful if we could prune directories from the MMIF storage, perhaps with a shell command prune that runs on the current directory.

Pruning should also update the index.

Once a job is finished the index should be updated.


### ClamShell on Aristotle

To properly test this you need a machine with a recent GPU that is big enough. It is possible to run small GPU jobs on child.cs-i.brandeis.edu but the GPU is old and not supported by Torch anymore and there are only a few configurations of CUDA and Torch that work, and it becomes especially hairy with containers. The best option is aristotle.cs-i.brandeis.edu, which is newer and more powerful so running containers there should be no problem.

On aristotle there is a script `/usr/local/bin/clamspod` which takes an image and a port number and then starts a Podman container that has a whole bunch of settings and mounts that make the container run for any CLAMS App. For example

```bash
clamspod ghcr.io/clamsproject/app-swt-detection:v8.6 5050
```

Typically you need to get a fairly high port number, using 5001 is likely to fail.

With the above the scipt will try to grab and use all GPU cores, but since these apps can only use one core it makes sense to grab a core that is not being used. Use `nvidia-smi` or `nvitop` to check what GPU cores are available, and then amend the command a bit:

```bash
CUDA_VISIBLE_DEVICES=1 clamspod ghcr.io/clamsproject/app-swt-detection:v8.6 5050
```

You may want to add another mount for local data and detach the container. Local data means local to aristotle which has a different file system than the OSX system used in the examples above. So let's assume that instead of `/Users/Shared/aapb/assets-small/` we have the assets stored in `/home/marc/data/aapb/assets-small`.

Now you can use (here we also added a name for the container):

```bash
clamspod ghcr.io/clamsproject/app-swt-detection:v8.6 5050 --name swt-8.6 -d -v /marc/home/data/aapb/assets-small:/data
```

With the above the actual run command that runs is

```bash
podman run \
	--pids-limit 16384 \
	--device nvidia.com/gpu=all \
	--security-opt=label=disable \
	-e TRITON_LIBCUDA_PATH=/lib64/libcuda.so.1 \
	-e BAAPB_RESOLVER_ADDRESS=eldrad.cs-i.brandeis.edu:23456 \
	-v /home/marc:/home/marc \
	-v /mnt/llc/llc_data:/mnt/llc/llc_data \
	-v /localcache/shared/torch_home:/cache/torch \
	-v /localcache/shared/whisper:/cache/whisper \
	-v /localcache/shared/hf_cache/hub:/cache/huggingface/hub \
	--rm \
	-p 20001:5000 \
	-d \
	-v /home/marc/data:/data \
	ghcr.io/clamsproject/app-swt-detection:v8.6 /bin/bash \
	-c 'pip3 install mmif-docloc-baapb && python3 /app/app.py'
```

When this is started and you run `nvidia-smi` again you will not notice that an extra GPU is used, this is because the model will not be loaded (and the GPU grabbed) until you first process something.

Formatted listing of running containers:

```bash
podman ps --format 'table {{.ID}} {{.Image}} {{.Names}} {{.Ports}}'
```

To check the container and its mounts use

```bash
podman exec -it <container_name>
```


### Debugging the Shack on Aristotle

Let's first get some real data on there to run by copying the local mini-archive from OSX to aristotle:

```bash
scp /Users/Shared/archive.tar.gz aristotle:/home/marc/data/aapb
```

After it is unpacked we can mount `/home/marc/data/aapb/archive`.

```bash
clamspod ghcr.io/clamsproject/app-swt-detection:v8.6 5050 --name swt -d -v /home/marc/data/aapb/archive:/data
```

Let's pull SWT, the captioner and spaCy, and then start the containers:

```bash
podman pull ghcr.io/clamsproject/app-swt-detection:v8.6
podman pull ghcr.io/clamsproject/app-smolvlm2-captioner:v1.0
podman pull  ghcr.io/clamsproject/app-spacy-wrapper:v2.2
clamspod ghcr.io/clamsproject/app-swt-detection:v8.6 5050 --name swt -d -v /home/marc/data/aapb/sample:/data
clamspod ghcr.io/clamsproject/app-smolvlm2-captioner:v1.0 5051 --name captioner -d -v /home/marc/data/aapb/sample:/data
clamspod ghcr.io/clamsproject/app-spacy-wrapper:v2.2 5052 --name spacy -d -v /home/marc/data/aapb/sample:/data
```

And let's create a new assets file tailored to the few text and video in there:

```
/home/marc/data/aapb/archive
video/cpb-aacip-507-z31ng4hp5t.part.mp4
text/cpb-aacip-507-z31ng4hp5t.part.mp4
```

Using the container in isolation:

```bash
curl -X POST -d@test/sources/cpb-aacip-507-z31ng4hp5t.part.mmif 127.0.0.1:5050 > out.json
```

And now create a Shack:

```
uv run python -m api.cli --shack test --assets assets2.txt
```

This does create an appropriate shack with 1 source and 2 assets.

```
clamshack> register http://127.0.0.1:5050
clamshack> register http://127.0.0.1:5051
clamshack> register http://127.0.0.1:5052
```


### Search

Distinguish between several kinds of search.

- Asset search on GUIDs. This is already implemented.
- MMIF file search on GUIDs, apps and workflow properties. The first could be folded into the asset search. On apps and/or workflow properties we should search every part of the workflow, for example, a spaCy result is still a spaCy result if it is in the last step of a workflow.
- Searchig the contents of the parameter files.
- A mix of search inputs, for example GUIDs and apps.


### Jobs

One thing that happens when you run a job is that the api storage code will not use the `STORAGE_DIR` environment variable. This is so we can isolate this better. The upload code was adjusted for this.

Todo:

- Jobs overide prior results, perhaps add a flag as with the storage upload to allow/disallow overwrite.
- They are less fragile than they used to be, but should still consider using a Job class that reads the job file and perhaps some changes to the format and content of the job file: (1) separate lines to represent things like batch info, app name, parameters etcetera, (2) add a count of files to be processed (allows later inspection of the file to print a percentage done number). 
- Make sure that files like '.DS_store' and others that are not jobs will be skipped, should be done in ClamShack


### Other

Q: When initializing also create .env?<br/>
A: No, because than you overwrite the current one, but maybe create .env-shack

When loading a shack assets names and MMIF files names are loaded, but the latter are not updated when we run jobs.