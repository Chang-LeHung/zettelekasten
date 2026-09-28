# Assets

Zett keeps two file libraries, and the difference matters when you decide where
something belongs.

| | Session assets | Static Assets |
| --- | --- | --- |
| Scope | One conversation | Every conversation |
| Shown in | The assets column of the workspace | The `Static Assets` view |
| Adding | Add text, add link, upload, or paste into a message | Upload to the library, then import |
| Importing elsewhere | — | Import by reference, without copying bytes |
| Deleting | Always allowed | Refused while a session asset still references it |

## Session assets

The assets column holds reference material for one conversation: notes, links,
documents, images, and code. Files are written under
`assets/sessions/<session-id>/`, so they are private to that session, and the
column can be hidden with the eye button in its header — the choice is kept in
local storage, not on the server.

You can also paste or drop files onto the message box. Those arrive as message
attachments: images render inline in the transcript, and every attachment is
written into the session's own upload directory at submit time, named by
submission time. The message keeps its inline data, and the file on disk is the
handle the Agent uses for a shell command or an image tool. These uploads are not
assets — they never appear in `list_assets` — and deleting the conversation
removes the whole session directory, so no orphan file is left behind.

The Agent reaches assets with its own tools (`create_asset`, `upload_asset`,
`get_asset`, `update_asset`, `delete_asset`, `list_assets`) and can reference one with `@` in
the composer, which reads it through the same tool rather than pasting its
content into the prompt.

## Static Assets

The `Static Assets` view is the global library: things that must outlive a
conversation and stay available everywhere, such as a paper you keep citing or a
template you reuse.

Uploading adds a file to the global library. Importing one into a conversation
creates a reference to the same stored object rather than a second copy, so
editing or re-uploading the original changes what every conversation sees, and
deleting a static asset is refused while a session still points at it.

The Agent publishes to this library through the local HTTP API instead of a
tool argument. Files it already wrote or compiled on disk are uploaded with a
shell command against `POST /api/assets/upload`, so binary content never has to
travel through the model's context as Base64. Importing a static asset back into
a conversation remains your action.

Search filters both libraries by name and type. Every stored location is an
object key relative to the storage root, and the only endpoint that streams
binary content is `/api/files/{key}` — absolute filesystem paths are never part
of a public model.

## Classifying a file

Files carry tags from their own collection tree: the artifact library and the
static asset library keep separate paths, so a collection you create here is not
one of the artifact library's, and neither ever lists or counts the other's.
Drag a file card in the `Static Assets` view onto a tag in the sidebar to add
that tag — the file keeps the tags it already carries, and the row shows them.
Dropping it on a tag it already has says so instead of rewriting the same set.

The API takes both shapes, exactly like artifacts: `PUT
/api/library/tags/assets/{asset_id}` replaces the complete set, while `PUT` and
`DELETE /api/library/tags/{tag_id}/assets/{asset_id}` attach or detach one tag
without touching the rest. This view browses its own collections: the sidebar
tree filters to the paths files actually use, counts only files, and clicking a
collection narrows the grid to it — a file collection never borrows the count of
an artifact, and the artifact library never shows a path only files use.

From a shell, the tag commands take `--asset` to name a file instead of an
artifact:

```bash
zett tag list
zett tag add --asset <asset-id> Engineering/Python
zett tag set --asset <asset-id> Projects/Zett Release
zett tag remove --asset <asset-id> Projects/Zett
```
