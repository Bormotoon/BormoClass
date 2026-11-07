# Google Classroom API REST Resources & Methods

> Complete list of resources, HTTP methods, paths, and descriptions.

## Resource: `registrations`

| Method | HTTP | Path | Description |
|---|---|---|---|
| `delete` | `DELETE` | `v1/registrations/{registrationId}` | Deletes a `Registration`, causing Classroom to stop sending notifications for that `Registration`. |
| `create` | `POST` | `v1/registrations` | Creates a `Registration`, causing Classroom to start sending notifications from the provided `feed` to the destination provided in `cloudPubSubTopic`. Returns the created `Registration`. Currently,... |


## Resource: `courses`

| Method | HTTP | Path | Description |
|---|---|---|---|
| `delete` | `DELETE` | `v1/courses/{id}` | Deletes a course. This method returns the following error codes: * `PERMISSION_DENIED` if the requesting user is not permitted to delete the requested course or for access errors. * `NOT_FOUND` if ... |
| `update` | `PUT` | `v1/courses/{id}` | Updates a course. Note: Unlike other fields, `levels` is not cleared if omitted from the request. The `UpdateCourse` method only modifies `levels` if it is explicitly provided; otherwise, the exist... |
| `create` | `POST` | `v1/courses` | Creates a course. The user specified in `ownerId` is the owner of the created course and added as a teacher. A non-admin requesting user can only create a course with themselves as the owner. Domai... |
| `patch` | `PATCH` | `v1/courses/{id}` | Updates one or more fields in a course. This method returns the following error codes: * `PERMISSION_DENIED` if the requesting user is not permitted to modify the requested course or for access err... |
| `list` | `GET` | `v1/courses` | Returns a list of courses that the requesting user is permitted to view, restricted to those that match the request. Returned courses are ordered by creation time, with the most recently created co... |
| `updateGradingPeriodSettings` | `PATCH` | `v1/courses/{courseId}/gradingPeriodSettings` | Updates grading period settings of a course. Individual grading periods can be added, removed, or modified using this method. The requesting user and course owner must be eligible to modify Grading... |
| `get` | `GET` | `v1/courses/{id}` | Returns a course. This method returns the following error codes: * `PERMISSION_DENIED` if the requesting user is not permitted to access the requested course or for access errors. * `NOT_FOUND` if ... |
| `getGradingPeriodSettings` | `GET` | `v1/courses/{courseId}/gradingPeriodSettings` | Returns the grading period settings in a course. This method returns the following error codes: * `PERMISSION_DENIED` if the requesting user isn't permitted to access the grading period settings in... |


## Resource: `courses.teachers`

| Method | HTTP | Path | Description |
|---|---|---|---|
| `get` | `GET` | `v1/courses/{courseId}/teachers/{userId}` | Returns a teacher of a course. This method returns the following error codes: * `PERMISSION_DENIED` if the requesting user is not permitted to view teachers of this course or for access errors. * `... |
| `create` | `POST` | `v1/courses/{courseId}/teachers` | Creates a teacher of a course. Domain administrators are permitted to [directly add](https://developers.google.com/workspace/classroom/guides/manage-users) users within their domain as teachers to ... |
| `list` | `GET` | `v1/courses/{courseId}/teachers` | Returns a list of teachers of this course that the requester is permitted to view. This method returns the following error codes: * `NOT_FOUND` if the course does not exist. * `PERMISSION_DENIED` f... |
| `delete` | `DELETE` | `v1/courses/{courseId}/teachers/{userId}` | Removes the specified teacher from the specified course. This method returns the following error codes: * `PERMISSION_DENIED` if the requesting user is not permitted to delete teachers of this cour... |


## Resource: `courses.aliases`

| Method | HTTP | Path | Description |
|---|---|---|---|
| `list` | `GET` | `v1/courses/{courseId}/aliases` | Returns a list of aliases for a course. This method returns the following error codes: * `PERMISSION_DENIED` if the requesting user is not permitted to access the course or for access errors. * `NO... |
| `create` | `POST` | `v1/courses/{courseId}/aliases` | Creates an alias for a course. This method returns the following error codes: * `PERMISSION_DENIED` if the requesting user is not permitted to create the alias or for access errors. * `NOT_FOUND` i... |
| `delete` | `DELETE` | `v1/courses/{courseId}/aliases/{alias}` | Deletes an alias of a course. This method returns the following error codes: * `PERMISSION_DENIED` if the requesting user is not permitted to remove the alias or for access errors. * `NOT_FOUND` if... |


## Resource: `courses.studentGroups`

| Method | HTTP | Path | Description |
|---|---|---|---|
| `list` | `GET` | `v1/courses/{courseId}/studentGroups` | Returns a list of groups in a course. This method returns the following error codes: * `NOT_FOUND` if the course does not exist. |
| `delete` | `DELETE` | `v1/courses/{courseId}/studentGroups/{id}` | Deletes a student group. This method returns the following error codes: * `PERMISSION_DENIED` if the requesting user is not permitted to delete the requested student group or for access errors. * `... |
| `patch` | `PATCH` | `v1/courses/{courseId}/studentGroups/{id}` | Updates one or more fields in a student group. This method returns the following error codes: * `PERMISSION_DENIED` if the requesting user is not permitted to modify the requested student group or ... |
| `create` | `POST` | `v1/courses/{courseId}/studentGroups` | Creates a student group for a course. This method returns the following error codes: * `PERMISSION_DENIED` if the requesting user is not permitted to create the student group or for access errors. ... |


## Resource: `courses.studentGroups.studentGroupMembers`

| Method | HTTP | Path | Description |
|---|---|---|---|
| `list` | `GET` | `v1/courses/{courseId}/studentGroups/{studentGroupId}/studentGroupMembers` | Returns a list of students in a group. This method returns the following error codes: * `NOT_FOUND` if the course or student group does not exist. |
| `delete` | `DELETE` | `v1/courses/{courseId}/studentGroups/{studentGroupId}/studentGroupMembers/{userId}` | Deletes a student group member. This method returns the following error codes: * `PERMISSION_DENIED` if the requesting user is not permitted to delete the requested student group member or for acce... |
| `create` | `POST` | `v1/courses/{courseId}/studentGroups/{studentGroupId}/studentGroupMembers` | Creates a student group member for a student group. This method returns the following error codes: * `PERMISSION_DENIED` if the requesting user is not permitted to create the student group or membe... |


## Resource: `courses.posts`

| Method | HTTP | Path | Description |
|---|---|---|---|
| `getAddOnContext` | `GET` | `v1/courses/{courseId}/posts/{postId}/addOnContext` | Gets metadata for Classroom add-ons in the context of a specific post. To maintain the integrity of its own data and permissions model, an add-on should call this to validate query parameters and t... |


## Resource: `courses.posts.addOnAttachments`

| Method | HTTP | Path | Description |
|---|---|---|---|
| `patch` | `PATCH` | `v1/courses/{courseId}/posts/{postId}/addOnAttachments/{attachmentId}` | Updates an add-on attachment. Requires the add-on to have been the original creator of the attachment. This method returns the following error codes: * `PERMISSION_DENIED` for access errors. * `INV... |
| `create` | `POST` | `v1/courses/{courseId}/posts/{postId}/addOnAttachments` | Creates an add-on attachment under a post. Requires the add-on to have permission to create new attachments on the post. This method returns the following error codes: * `PERMISSION_DENIED` for acc... |
| `list` | `GET` | `v1/courses/{courseId}/posts/{postId}/addOnAttachments` | Returns all attachments created by an add-on under the post. Requires the add-on to have active attachments on the post or have permission to create new attachments on the post. This method returns... |
| `delete` | `DELETE` | `v1/courses/{courseId}/posts/{postId}/addOnAttachments/{attachmentId}` | Deletes an add-on attachment. Requires the add-on to have been the original creator of the attachment. This method returns the following error codes: * `PERMISSION_DENIED` for access errors. * `INV... |
| `get` | `GET` | `v1/courses/{courseId}/posts/{postId}/addOnAttachments/{attachmentId}` | Returns an add-on attachment. Requires the add-on requesting the attachment to be the original creator of the attachment. This method returns the following error codes: * `PERMISSION_DENIED` for ac... |


## Resource: `courses.posts.addOnAttachments.studentSubmissions`

| Method | HTTP | Path | Description |
|---|---|---|---|
| `patch` | `PATCH` | `v1/courses/{courseId}/posts/{postId}/addOnAttachments/{attachmentId}/studentSubmissions/{submissionId}` | Updates data associated with an add-on attachment submission. Requires the add-on to have been the original creator of the attachment and the attachment to have a positive `max_points` value set. T... |
| `get` | `GET` | `v1/courses/{courseId}/posts/{postId}/addOnAttachments/{attachmentId}/studentSubmissions/{submissionId}` | Returns a student submission for an add-on attachment. This method returns the following error codes: * `PERMISSION_DENIED` for access errors. * `INVALID_ARGUMENT` if the request is malformed. * `N... |


## Resource: `courses.courseWork`

| Method | HTTP | Path | Description |
|---|---|---|---|
| `patch` | `PATCH` | `v1/courses/{courseId}/courseWork/{id}` | Updates one or more fields of a course work. See google.classroom.v1.CourseWork for details of which fields may be updated and who may change them. This request must be made by the Developer Consol... |
| `modifyAssignees` | `POST` | `v1/courses/{courseId}/courseWork/{id}:modifyAssignees` | Modifies assignee mode and options of a coursework. Only a teacher of the course that contains the coursework may call this method. This method returns the following error codes: * `PERMISSION_DENI... |
| `create` | `POST` | `v1/courses/{courseId}/courseWork` | Creates course work. The resulting course work (and corresponding student submissions) are associated with the Developer Console project of the [OAuth client ID](https://support.google.com/cloud/an... |
| `getAddOnContext` | `GET` | `v1/courses/{courseId}/courseWork/{itemId}/addOnContext` | Gets metadata for Classroom add-ons in the context of a specific post. To maintain the integrity of its own data and permissions model, an add-on should call this to validate query parameters and t... |
| `get` | `GET` | `v1/courses/{courseId}/courseWork/{id}` | Returns course work. This method returns the following error codes: * `PERMISSION_DENIED` if the requesting user is not permitted to access the requested course or course work, or for access errors... |
| `list` | `GET` | `v1/courses/{courseId}/courseWork` | Returns a list of course work that the requester is permitted to view. Course students may only view `PUBLISHED` course work. Course teachers and domain administrators may view all course work. Thi... |
| `updateRubric` | `PATCH` | `v1/courses/{courseId}/courseWork/{courseWorkId}/rubric` | Updates a rubric. See google.classroom.v1.Rubric for details of which fields can be updated. Rubric update capabilities are [limited](/classroom/rubrics/limitations) once grading has started. The r... |
| `delete` | `DELETE` | `v1/courses/{courseId}/courseWork/{id}` | Deletes a course work. This request must be made by the Developer Console project of the [OAuth client ID](https://support.google.com/cloud/answer/6158849) used to create the corresponding course w... |


## Resource: `courses.courseWork.addOnAttachments`

| Method | HTTP | Path | Description |
|---|---|---|---|
| `delete` | `DELETE` | `v1/courses/{courseId}/courseWork/{itemId}/addOnAttachments/{attachmentId}` | Deletes an add-on attachment. Requires the add-on to have been the original creator of the attachment. This method returns the following error codes: * `PERMISSION_DENIED` for access errors. * `INV... |
| `list` | `GET` | `v1/courses/{courseId}/courseWork/{itemId}/addOnAttachments` | Returns all attachments created by an add-on under the post. Requires the add-on to have active attachments on the post or have permission to create new attachments on the post. This method returns... |
| `create` | `POST` | `v1/courses/{courseId}/courseWork/{itemId}/addOnAttachments` | Creates an add-on attachment under a post. Requires the add-on to have permission to create new attachments on the post. This method returns the following error codes: * `PERMISSION_DENIED` for acc... |
| `patch` | `PATCH` | `v1/courses/{courseId}/courseWork/{itemId}/addOnAttachments/{attachmentId}` | Updates an add-on attachment. Requires the add-on to have been the original creator of the attachment. This method returns the following error codes: * `PERMISSION_DENIED` for access errors. * `INV... |
| `get` | `GET` | `v1/courses/{courseId}/courseWork/{itemId}/addOnAttachments/{attachmentId}` | Returns an add-on attachment. Requires the add-on requesting the attachment to be the original creator of the attachment. This method returns the following error codes: * `PERMISSION_DENIED` for ac... |


## Resource: `courses.courseWork.addOnAttachments.studentSubmissions`

| Method | HTTP | Path | Description |
|---|---|---|---|
| `get` | `GET` | `v1/courses/{courseId}/courseWork/{itemId}/addOnAttachments/{attachmentId}/studentSubmissions/{submissionId}` | Returns a student submission for an add-on attachment. This method returns the following error codes: * `PERMISSION_DENIED` for access errors. * `INVALID_ARGUMENT` if the request is malformed. * `N... |
| `list` | `GET` | `v1/courses/{courseId}/courseWork/{itemId}/addOnAttachments/{attachmentId}/studentSubmissions` | Returns a list of student submissions that the requester is permitted to view. This method returns the following error codes: * `PERMISSION_DENIED` for access errors. * `INVALID_ARGUMENT` if the re... |
| `patch` | `PATCH` | `v1/courses/{courseId}/courseWork/{itemId}/addOnAttachments/{attachmentId}/studentSubmissions/{submissionId}` | Updates data associated with an add-on attachment submission. Requires the add-on to have been the original creator of the attachment and the attachment to have a positive `max_points` value set. T... |


## Resource: `courses.courseWork.rubrics`

| Method | HTTP | Path | Description |
|---|---|---|---|
| `list` | `GET` | `v1/courses/{courseId}/courseWork/{courseWorkId}/rubrics` | Returns a list of rubrics that the requester is permitted to view. This method returns the following error codes: * `PERMISSION_DENIED` for access errors. * `INVALID_ARGUMENT` if the request is mal... |
| `patch` | `PATCH` | `v1/courses/{courseId}/courseWork/{courseWorkId}/rubrics/{id}` | Updates a rubric. See google.classroom.v1.Rubric for details of which fields can be updated. Rubric update capabilities are [limited](/classroom/rubrics/limitations) once grading has started. The r... |
| `delete` | `DELETE` | `v1/courses/{courseId}/courseWork/{courseWorkId}/rubrics/{id}` | Deletes a rubric. The requesting user and course owner must have rubrics creation capabilities. For details, see [licensing requirements](https://developers.google.com/workspace/classroom/rubrics/l... |
| `get` | `GET` | `v1/courses/{courseId}/courseWork/{courseWorkId}/rubrics/{id}` | Returns a rubric. This method returns the following error codes: * `PERMISSION_DENIED` for access errors. * `INVALID_ARGUMENT` if the request is malformed. * `NOT_FOUND` if the requested course, co... |
| `create` | `POST` | `v1/courses/{courseId}/courseWork/{courseWorkId}/rubrics` | Creates a rubric. The requesting user and course owner must have rubrics creation capabilities. For details, see [licensing requirements](https://developers.google.com/workspace/classroom/rubrics/l... |


## Resource: `courses.courseWork.studentSubmissions`

| Method | HTTP | Path | Description |
|---|---|---|---|
| `return` | `POST` | `v1/courses/{courseId}/courseWork/{courseWorkId}/studentSubmissions/{id}:return` | Returns a student submission. Returning a student submission transfers ownership of attached Drive files to the student and may also update the submission state. Unlike the Classroom application, r... |
| `list` | `GET` | `v1/courses/{courseId}/courseWork/{courseWorkId}/studentSubmissions` | Returns a list of student submissions that the requester is permitted to view, factoring in the OAuth scopes of the request. A hyphen (`-`) may be specified as the `course_work_id` to include stude... |
| `patch` | `PATCH` | `v1/courses/{courseId}/courseWork/{courseWorkId}/studentSubmissions/{id}` | Updates one or more fields of a student submission. See google.classroom.v1.StudentSubmission for details of which fields may be updated and who may change them. This request must be made by the De... |
| `modifyAttachments` | `POST` | `v1/courses/{courseId}/courseWork/{courseWorkId}/studentSubmissions/{id}:modifyAttachments` | Modifies attachments of student submission. Attachments may only be added to student submissions belonging to course work objects with a `workType` of `ASSIGNMENT`. This request must be made by the... |
| `get` | `GET` | `v1/courses/{courseId}/courseWork/{courseWorkId}/studentSubmissions/{id}` | Returns a student submission. * `PERMISSION_DENIED` if the requesting user is not permitted to access the requested course, course work, or student submission or for access errors. * `INVALID_ARGUM... |
| `turnIn` | `POST` | `v1/courses/{courseId}/courseWork/{courseWorkId}/studentSubmissions/{id}:turnIn` | Turns in a student submission. Turning in a student submission transfers ownership of attached Drive files to the teacher and may also update the submission state. This may only be called by the st... |
| `reclaim` | `POST` | `v1/courses/{courseId}/courseWork/{courseWorkId}/studentSubmissions/{id}:reclaim` | Reclaims a student submission on behalf of the student that owns it. Reclaiming a student submission transfers ownership of attached Drive files to the student and updates the submission state. Onl... |


## Resource: `courses.courseWorkMaterials`

| Method | HTTP | Path | Description |
|---|---|---|---|
| `list` | `GET` | `v1/courses/{courseId}/courseWorkMaterials` | Returns a list of course work material that the requester is permitted to view. Course students may only view `PUBLISHED` course work material. Course teachers and domain administrators may view al... |
| `get` | `GET` | `v1/courses/{courseId}/courseWorkMaterials/{id}` | Returns a course work material. This method returns the following error codes: * `PERMISSION_DENIED` if the requesting user is not permitted to access the requested course or course work material, ... |
| `delete` | `DELETE` | `v1/courses/{courseId}/courseWorkMaterials/{id}` | Deletes a course work material. This request must be made by the Developer Console project of the [OAuth client ID](https://support.google.com/cloud/answer/6158849) used to create the corresponding... |
| `getAddOnContext` | `GET` | `v1/courses/{courseId}/courseWorkMaterials/{itemId}/addOnContext` | Gets metadata for Classroom add-ons in the context of a specific post. To maintain the integrity of its own data and permissions model, an add-on should call this to validate query parameters and t... |
| `patch` | `PATCH` | `v1/courses/{courseId}/courseWorkMaterials/{id}` | Updates one or more fields of a course work material. This method returns the following error codes: * `PERMISSION_DENIED` if the requesting developer project for access errors. * `INVALID_ARGUMENT... |
| `create` | `POST` | `v1/courses/{courseId}/courseWorkMaterials` | Creates a course work material. This method returns the following error codes: * `PERMISSION_DENIED` if the requesting user is not permitted to access the requested course, create course work mater... |


## Resource: `courses.courseWorkMaterials.addOnAttachments`

| Method | HTTP | Path | Description |
|---|---|---|---|
| `get` | `GET` | `v1/courses/{courseId}/courseWorkMaterials/{itemId}/addOnAttachments/{attachmentId}` | Returns an add-on attachment. Requires the add-on requesting the attachment to be the original creator of the attachment. This method returns the following error codes: * `PERMISSION_DENIED` for ac... |
| `list` | `GET` | `v1/courses/{courseId}/courseWorkMaterials/{itemId}/addOnAttachments` | Returns all attachments created by an add-on under the post. Requires the add-on to have active attachments on the post or have permission to create new attachments on the post. This method returns... |
| `create` | `POST` | `v1/courses/{courseId}/courseWorkMaterials/{itemId}/addOnAttachments` | Creates an add-on attachment under a post. Requires the add-on to have permission to create new attachments on the post. This method returns the following error codes: * `PERMISSION_DENIED` for acc... |
| `patch` | `PATCH` | `v1/courses/{courseId}/courseWorkMaterials/{itemId}/addOnAttachments/{attachmentId}` | Updates an add-on attachment. Requires the add-on to have been the original creator of the attachment. This method returns the following error codes: * `PERMISSION_DENIED` for access errors. * `INV... |
| `delete` | `DELETE` | `v1/courses/{courseId}/courseWorkMaterials/{itemId}/addOnAttachments/{attachmentId}` | Deletes an add-on attachment. Requires the add-on to have been the original creator of the attachment. This method returns the following error codes: * `PERMISSION_DENIED` for access errors. * `INV... |


## Resource: `courses.topics`

| Method | HTTP | Path | Description |
|---|---|---|---|
| `create` | `POST` | `v1/courses/{courseId}/topics` | Creates a topic. This method returns the following error codes: * `PERMISSION_DENIED` if the requesting user is not permitted to access the requested course, create a topic in the requested course,... |
| `get` | `GET` | `v1/courses/{courseId}/topics/{id}` | Returns a topic. This method returns the following error codes: * `PERMISSION_DENIED` if the requesting user is not permitted to access the requested course or topic, or for access errors. * `INVAL... |
| `list` | `GET` | `v1/courses/{courseId}/topics` | Returns the list of topics that the requester is permitted to view. This method returns the following error codes: * `PERMISSION_DENIED` if the requesting user is not permitted to access the reques... |
| `patch` | `PATCH` | `v1/courses/{courseId}/topics/{id}` | Updates one or more fields of a topic. This method returns the following error codes: * `PERMISSION_DENIED` if the requesting developer project did not create the corresponding topic or for access ... |
| `delete` | `DELETE` | `v1/courses/{courseId}/topics/{id}` | Deletes a topic. This method returns the following error codes: * `PERMISSION_DENIED` if the requesting user is not allowed to delete the requested topic or for access errors. * `FAILED_PRECONDITIO... |


## Resource: `courses.students`

| Method | HTTP | Path | Description |
|---|---|---|---|
| `get` | `GET` | `v1/courses/{courseId}/students/{userId}` | Returns a student of a course. This method returns the following error codes: * `PERMISSION_DENIED` if the requesting user is not permitted to view students of this course or for access errors. * `... |
| `list` | `GET` | `v1/courses/{courseId}/students` | Returns a list of students of this course that the requester is permitted to view. This method returns the following error codes: * `NOT_FOUND` if the course does not exist. * `PERMISSION_DENIED` f... |
| `delete` | `DELETE` | `v1/courses/{courseId}/students/{userId}` | Deletes a student of a course. This method returns the following error codes: * `PERMISSION_DENIED` if the requesting user is not permitted to delete students of this course or for access errors. *... |
| `create` | `POST` | `v1/courses/{courseId}/students` | Adds a user as a student of a course. Domain administrators are permitted to [directly add](https://developers.google.com/workspace/classroom/guides/manage-users) users within their domain as stude... |


## Resource: `courses.announcements`

| Method | HTTP | Path | Description |
|---|---|---|---|
| `getAddOnContext` | `GET` | `v1/courses/{courseId}/announcements/{itemId}/addOnContext` | Gets metadata for Classroom add-ons in the context of a specific post. To maintain the integrity of its own data and permissions model, an add-on should call this to validate query parameters and t... |
| `patch` | `PATCH` | `v1/courses/{courseId}/announcements/{id}` | Updates one or more fields of an announcement. This method returns the following error codes: * `PERMISSION_DENIED` if the requesting developer project did not create the corresponding announcement... |
| `modifyAssignees` | `POST` | `v1/courses/{courseId}/announcements/{id}:modifyAssignees` | Modifies assignee mode and options of an announcement. Only a teacher of the course that contains the announcement may call this method. This method returns the following error codes: * `PERMISSION... |
| `delete` | `DELETE` | `v1/courses/{courseId}/announcements/{id}` | Deletes an announcement. This request must be made by the Developer Console project of the [OAuth client ID](https://support.google.com/cloud/answer/6158849) used to create the corresponding announ... |
| `list` | `GET` | `v1/courses/{courseId}/announcements` | Returns a list of announcements that the requester is permitted to view. Course students may only view `PUBLISHED` announcements. Course teachers and domain administrators may view all announcement... |
| `get` | `GET` | `v1/courses/{courseId}/announcements/{id}` | Returns an announcement. This method returns the following error codes: * `PERMISSION_DENIED` if the requesting user is not permitted to access the requested course or announcement, or for access e... |
| `create` | `POST` | `v1/courses/{courseId}/announcements` | Creates an announcement. This method returns the following error codes: * `PERMISSION_DENIED` if the requesting user is not permitted to access the requested course, create announcements in the req... |


## Resource: `courses.announcements.addOnAttachments`

| Method | HTTP | Path | Description |
|---|---|---|---|
| `patch` | `PATCH` | `v1/courses/{courseId}/announcements/{itemId}/addOnAttachments/{attachmentId}` | Updates an add-on attachment. Requires the add-on to have been the original creator of the attachment. This method returns the following error codes: * `PERMISSION_DENIED` for access errors. * `INV... |
| `create` | `POST` | `v1/courses/{courseId}/announcements/{itemId}/addOnAttachments` | Creates an add-on attachment under a post. Requires the add-on to have permission to create new attachments on the post. This method returns the following error codes: * `PERMISSION_DENIED` for acc... |
| `list` | `GET` | `v1/courses/{courseId}/announcements/{itemId}/addOnAttachments` | Returns all attachments created by an add-on under the post. Requires the add-on to have active attachments on the post or have permission to create new attachments on the post. This method returns... |
| `delete` | `DELETE` | `v1/courses/{courseId}/announcements/{itemId}/addOnAttachments/{attachmentId}` | Deletes an add-on attachment. Requires the add-on to have been the original creator of the attachment. This method returns the following error codes: * `PERMISSION_DENIED` for access errors. * `INV... |
| `get` | `GET` | `v1/courses/{courseId}/announcements/{itemId}/addOnAttachments/{attachmentId}` | Returns an add-on attachment. Requires the add-on requesting the attachment to be the original creator of the attachment. This method returns the following error codes: * `PERMISSION_DENIED` for ac... |


## Resource: `invitations`

| Method | HTTP | Path | Description |
|---|---|---|---|
| `create` | `POST` | `v1/invitations` | Creates an invitation. Only one invitation for a user and course may exist at a time. Delete and re-create an invitation to make changes. This method returns the following error codes: * `PERMISSIO... |
| `accept` | `POST` | `v1/invitations/{id}:accept` | Accepts an invitation, removing it and adding the invited user to the teachers or students (as appropriate) of the specified course. Only the invited user may accept an invitation. This method retu... |
| `list` | `GET` | `v1/invitations` | Returns a list of invitations that the requesting user is permitted to view, restricted to those that match the list request. *Note:* At least one of `user_id` or `course_id` must be supplied. Both... |
| `get` | `GET` | `v1/invitations/{id}` | Returns an invitation. This method returns the following error codes: * `PERMISSION_DENIED` if the requesting user is not permitted to view the requested invitation or for access errors. * `NOT_FOU... |
| `delete` | `DELETE` | `v1/invitations/{id}` | Deletes an invitation. This method returns the following error codes: * `PERMISSION_DENIED` if the requesting user is not permitted to delete the requested invitation or for access errors. * `NOT_F... |


## Resource: `userProfiles`

| Method | HTTP | Path | Description |
|---|---|---|---|
| `get` | `GET` | `v1/userProfiles/{userId}` | Returns a user profile. This method returns the following error codes: * `PERMISSION_DENIED` if the requesting user is not permitted to access this user profile, if no profile exists with the reque... |


## Resource: `userProfiles.guardians`

| Method | HTTP | Path | Description |
|---|---|---|---|
| `list` | `GET` | `v1/userProfiles/{studentId}/guardians` | Returns a list of guardians that the requesting user is permitted to view, restricted to those that match the request. To list guardians for any student that the requesting user may view guardians ... |
| `get` | `GET` | `v1/userProfiles/{studentId}/guardians/{guardianId}` | Returns a specific guardian. This method returns the following error codes: * `PERMISSION_DENIED` if no user that matches the provided `student_id` is visible to the requesting user, if the request... |
| `delete` | `DELETE` | `v1/userProfiles/{studentId}/guardians/{guardianId}` | Deletes a guardian. The guardian will no longer receive guardian notifications and the guardian will no longer be accessible via the API. This method returns the following error codes: * `PERMISSIO... |


## Resource: `userProfiles.guardianInvitations`

| Method | HTTP | Path | Description |
|---|---|---|---|
| `patch` | `PATCH` | `v1/userProfiles/{studentId}/guardianInvitations/{invitationId}` | Modifies a guardian invitation. Currently, the only valid modification is to change the `state` from `PENDING` to `COMPLETE`. This has the effect of withdrawing the invitation. This method returns ... |
| `list` | `GET` | `v1/userProfiles/{studentId}/guardianInvitations` | Returns a list of guardian invitations that the requesting user is permitted to view, filtered by the parameters provided. This method returns the following error codes: * `PERMISSION_DENIED` if a ... |
| `create` | `POST` | `v1/userProfiles/{studentId}/guardianInvitations` | Creates a guardian invitation, and sends an email to the guardian asking them to confirm that they are the student's guardian. Once the guardian accepts the invitation, their `state` will change to... |
| `get` | `GET` | `v1/userProfiles/{studentId}/guardianInvitations/{invitationId}` | Returns a specific guardian invitation. This method returns the following error codes: * `PERMISSION_DENIED` if the requesting user is not permitted to view guardian invitations for the student ide... |

