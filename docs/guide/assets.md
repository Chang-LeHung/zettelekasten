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
