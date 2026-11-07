# Google Classroom API Data Schemas

> Generated from official Google Classroom API v1 Discovery Document.
> Total Schemas: **85**

## Table of Contents

- [AddOnAttachment](#addonattachment)
- [AddOnAttachmentStudentSubmission](#addonattachmentstudentsubmission)
- [AddOnContext](#addoncontext)
- [Announcement](#announcement)
- [Assignment](#assignment)
- [AssignmentSubmission](#assignmentsubmission)
- [Attachment](#attachment)
- [CloudPubsubTopic](#cloudpubsubtopic)
- [CopyHistory](#copyhistory)
- [Course](#course)
- [CourseAlias](#coursealias)
- [CourseMaterial](#coursematerial)
- [CourseMaterialSet](#coursematerialset)
- [CourseRosterChangesInfo](#courserosterchangesinfo)
- [CourseWork](#coursework)
- [CourseWorkChangesInfo](#courseworkchangesinfo)
- [CourseWorkMaterial](#courseworkmaterial)
- [Criterion](#criterion)
- [Date](#date)
- [DriveFile](#drivefile)
- [DriveFolder](#drivefolder)
- [EmbedUri](#embeduri)
- [Empty](#empty)
- [Feed](#feed)
- [Form](#form)
- [GeminiGem](#geminigem)
- [GlobalPermission](#globalpermission)
- [GradeCategory](#gradecategory)
- [GradeHistory](#gradehistory)
- [GradebookSettings](#gradebooksettings)
- [GradingPeriod](#gradingperiod)
- [GradingPeriodSettings](#gradingperiodsettings)
- [Guardian](#guardian)
- [GuardianInvitation](#guardianinvitation)
- [IndividualStudentsOptions](#individualstudentsoptions)
- [Invitation](#invitation)
- [Level](#level)
- [Link](#link)
- [ListAddOnAttachmentStudentSubmissionsResponse](#listaddonattachmentstudentsubmissionsresponse)
- [ListAddOnAttachmentsResponse](#listaddonattachmentsresponse)
- [ListAnnouncementsResponse](#listannouncementsresponse)
- [ListCourseAliasesResponse](#listcoursealiasesresponse)
- [ListCourseWorkMaterialResponse](#listcourseworkmaterialresponse)
- [ListCourseWorkResponse](#listcourseworkresponse)
- [ListCoursesResponse](#listcoursesresponse)
- [ListGuardianInvitationsResponse](#listguardianinvitationsresponse)
- [ListGuardiansResponse](#listguardiansresponse)
- [ListInvitationsResponse](#listinvitationsresponse)
- [ListRubricsResponse](#listrubricsresponse)
- [ListStudentGroupMembersResponse](#liststudentgroupmembersresponse)
- [ListStudentGroupsResponse](#liststudentgroupsresponse)
- [ListStudentSubmissionsResponse](#liststudentsubmissionsresponse)
- [ListStudentsResponse](#liststudentsresponse)
- [ListTeachersResponse](#listteachersresponse)
- [ListTopicResponse](#listtopicresponse)
- [Material](#material)
- [ModifyAnnouncementAssigneesRequest](#modifyannouncementassigneesrequest)
- [ModifyAttachmentsRequest](#modifyattachmentsrequest)
- [ModifyCourseWorkAssigneesRequest](#modifycourseworkassigneesrequest)
- [ModifyIndividualStudentsOptions](#modifyindividualstudentsoptions)
- [MultipleChoiceQuestion](#multiplechoicequestion)
- [MultipleChoiceSubmission](#multiplechoicesubmission)
- [Name](#name)
- [NotebookLmNotebook](#notebooklmnotebook)
- [ReclaimStudentSubmissionRequest](#reclaimstudentsubmissionrequest)
- [Registration](#registration)
- [ReturnStudentSubmissionRequest](#returnstudentsubmissionrequest)
- [Rubric](#rubric)
- [RubricGrade](#rubricgrade)
- [SharedDriveFile](#shareddrivefile)
- [ShortAnswerSubmission](#shortanswersubmission)
- [StateHistory](#statehistory)
- [Student](#student)
- [StudentContext](#studentcontext)
- [StudentGroup](#studentgroup)
- [StudentGroupMember](#studentgroupmember)
- [StudentSubmission](#studentsubmission)
- [SubmissionHistory](#submissionhistory)
- [Teacher](#teacher)
- [TeacherContext](#teachercontext)
- [TimeOfDay](#timeofday)
- [Topic](#topic)
- [TurnInStudentSubmissionRequest](#turninstudentsubmissionrequest)
- [UserProfile](#userprofile)
- [YouTubeVideo](#youtubevideo)

---

## AddOnAttachment
**Type:** `object`

An add-on attachment on a post.

| Field | Type | Format / Enum | Description |
|---|---|---|---|
| `itemId` | string | - | Immutable. Identifier of the `Announcement`, `CourseWork`, or `CourseWorkMaterial` under which the attachment is attached. Unique per course. |
| `dueTime` | [`TimeOfDay`](#timeofday) | - | Time of day, in UTC, that work on this attachment is due. This must be specified if `due_date` is specified. |
| `dueDate` | [`Date`](#date) | - | Date, in UTC, that work on this attachment is due. This must be specified if `due_time` is specified. |
| `title` | string | - | Required. Title of this attachment. The title must be between 1 and 1000 characters. |
| `id` | string | - | Immutable. Classroom-assigned identifier for this attachment, unique per post. |
| `gradeSyncEnabled` | boolean | - | Output only. Whether changes to `pointsEarned` values on this attachment's student submissions will be copied to the `pointsEarned` field on the students' CourseWork submissions. This field can be `true` for at most one add-on attachment per stream item. |
| `copyHistory` | Array of [`CopyHistory`](#copyhistory) | - | Output only. Identifiers of attachments that were previous copies of this attachment. If the attachment was previously copied by virtue of its parent post being copied, this enumerates the identifiers of attachments that were its previous copies in ascending chronological order of copy. |
| `maxPoints` | number | double | Maximum grade for this attachment. Can only be set if `studentWorkReviewUri` is set. Set to a non-zero value to indicate that the attachment supports grade passback. If set, this must be a non-negative integer value. When set to zero, the attachment will not support grade passback. |
| `postId` | string | - | Immutable. Deprecated, use `item_id` instead. |
| `courseId` | string | - | Immutable. Identifier of the course. |
| `studentViewUri` | [`EmbedUri`](#embeduri) | - | Required. URI to show the student view of the attachment. The URI will be opened in an iframe with the `courseId`, `itemId`, `itemType`, and `attachmentId` query parameters set. |
| `teacherViewUri` | [`EmbedUri`](#embeduri) | - | Required. URI to show the teacher view of the attachment. The URI will be opened in an iframe with the `courseId`, `itemId`, `itemType`, and `attachmentId` query parameters set. |
| `studentWorkReviewUri` | [`EmbedUri`](#embeduri) | - | URI for the teacher to see student work on the attachment, if applicable. The URI will be opened in an iframe with the `courseId`, `itemId`, `itemType`, `attachmentId`, and `submissionId` query parameters set. This is the same `submissionId` returned in the [`AddOnContext.studentContext`](/worksp... |


---

## AddOnAttachmentStudentSubmission
**Type:** `object`

Payload for grade update requests.

| Field | Type | Format / Enum | Description |
|---|---|---|---|
| `id` | string | - | Output only. Classroom-assigned identifier for this student submission. This is unique among submissions for the relevant course work and add-on attachment combination. |
| `userId` | string | - | Identifier for the student that owns this submission. Requires the user to be a teacher in the course and have permission to read student submissions. See [`courseWork.studentSubmissions.get`](/workspace/classroom/reference/rest/v1/courses.courseWork.studentSubmissions/get#authorization-scopes) f... |
| `pointsEarned` | number | double | Student grade on this attachment. If unset, no grade was set. |
| `courseWorkSubmissionId` | string | - | Output only. Identifier of the course work submission under which this attachment submission was made. |
| `postSubmissionState` | string | `SUBMISSION_STATE_UNSPECIFIED`, `NEW`, `CREATED`, `TURNED_IN`, `RETURNED`, `RECLAIMED_BY_STUDENT` | Submission state of add-on attachment's parent post (i.e. assignment). |


---

## AddOnContext
**Type:** `object`

Attachment-relevant metadata for Classroom add-ons in the context of a specific post.

| Field | Type | Format / Enum | Description |
|---|---|---|---|
| `teacherContext` | [`TeacherContext`](#teachercontext) | - | Add-on context corresponding to the requesting user's role as a teacher. Its presence implies that the requesting user is a teacher in the course. |
| `studentContext` | [`StudentContext`](#studentcontext) | - | Add-on context corresponding to the requesting user's role as a student. Its presence implies that the requesting user is a student in the course. |
| `itemId` | string | - | Immutable. Identifier of the `Announcement`, `CourseWork`, or `CourseWorkMaterial` under which the attachment is attached. |
| `courseId` | string | - | Immutable. Identifier of the course. |
| `supportsStudentWork` | boolean | - | Optional. Whether the post allows the teacher to see student work and passback grades. |
| `postId` | string | - | Immutable. Deprecated, use `item_id` instead. |


---

## Announcement
**Type:** `object`

Announcement created by a teacher for students of the course

| Field | Type | Format / Enum | Description |
|---|---|---|---|
| `text` | string | - | Description of this announcement. The text must be a valid UTF-8 string containing no more than 30,000 characters. |
| `courseId` | string | - | Identifier of the course. Read-only. |
| `creatorUserId` | string | - | Identifier for the user that created the announcement. Read-only. |
| `individualStudentsOptions` | [`IndividualStudentsOptions`](#individualstudentsoptions) | - | Identifiers of students with access to the announcement. This field is set only if `assigneeMode` is `INDIVIDUAL_STUDENTS`. If the `assigneeMode` is `INDIVIDUAL_STUDENTS`, then only students specified in this field can see the announcement. |
| `alternateLink` | string | - | Absolute link to this announcement in the Classroom web UI. This is only populated if `state` is `PUBLISHED`. Read-only. |
| `creationTime` | string | google-datetime | Timestamp when this announcement was created. Read-only. |
| `assigneeMode` | string | `ASSIGNEE_MODE_UNSPECIFIED`, `ALL_STUDENTS`, `INDIVIDUAL_STUDENTS` | Assignee mode of the announcement. If unspecified, the default value is `ALL_STUDENTS`. |
| `id` | string | - | Classroom-assigned identifier of this announcement, unique per course. Read-only. |
| `materials` | Array of [`Material`](#material) | - | Additional materials. Announcements must have no more than 20 material items. |
| `state` | string | `ANNOUNCEMENT_STATE_UNSPECIFIED`, `PUBLISHED`, `DRAFT`, `DELETED` | Status of this announcement. If unspecified, the default state is `DRAFT`. |
| `updateTime` | string | google-datetime | Timestamp of the most recent change to this announcement. Read-only. |
| `scheduledTime` | string | google-datetime | Optional timestamp when this announcement is scheduled to be published. |


---

## Assignment
**Type:** `object`

Additional details for assignments.

| Field | Type | Format / Enum | Description |
|---|---|---|---|
| `studentWorkFolder` | [`DriveFolder`](#drivefolder) | - | Drive folder where attachments from student submissions are placed. This is only populated for course teachers and administrators. |


---

## AssignmentSubmission
**Type:** `object`

Student work for an assignment.

| Field | Type | Format / Enum | Description |
|---|---|---|---|
| `attachments` | Array of [`Attachment`](#attachment) | - | Attachments added by the student. Drive files that correspond to materials with a share mode of STUDENT_COPY may not exist yet if the student has not accessed the assignment in Classroom. Some attachment metadata is only populated if the requesting user has permission to access it. Identifier and... |


---

## Attachment
**Type:** `object`

Attachment added to student assignment work. When creating attachments, setting the `form` field is not supported.

| Field | Type | Format / Enum | Description |
|---|---|---|---|
| `form` | [`Form`](#form) | - | Google Forms attachment. |
| `link` | [`Link`](#link) | - | Link attachment. |
| `driveFile` | [`DriveFile`](#drivefile) | - | Google Drive file attachment. |
| `youTubeVideo` | [`YouTubeVideo`](#youtubevideo) | - | Youtube video attachment. |


---

## CloudPubsubTopic
**Type:** `object`

A reference to a Cloud Pub/Sub topic. To register for notifications, the owner of the topic must grant `classroom-notifications@system.gserviceaccount.com` the `projects.topics.publish` permission.

| Field | Type | Format / Enum | Description |
|---|---|---|---|
| `topicName` | string | - | The `name` field of a Cloud Pub/Sub [Topic](https://cloud.google.com/pubsub/docs/reference/rest/v1/projects.topics#Topic). |


---

## CopyHistory
**Type:** `object`

Identifier of a previous copy of a given attachment.

| Field | Type | Format / Enum | Description |
|---|---|---|---|
| `itemId` | string | - | Immutable. Identifier of the `Announcement`, `CourseWork`, or `CourseWorkMaterial` under which the attachment is attached. |
| `courseId` | string | - | Immutable. Identifier of the course. |
| `postId` | string | - | Immutable. Deprecated, use `item_id` instead. |
| `attachmentId` | string | - | Immutable. Identifier of the attachment. |


---

## Course
**Type:** `object`

A Course in Classroom.

| Field | Type | Format / Enum | Description |
|---|---|---|---|
| `id` | string | - | Identifier for this course assigned by Classroom. When creating a course, you may optionally set this identifier to an alias string in the request to create a corresponding alias. The `id` is still assigned by Classroom and cannot be updated after the course is created. Specifying this field in a... |
| `name` | string | - | Name of the course. For example, "10th Grade Biology". The name is required. It must be between 1 and 750 characters and a valid UTF-8 string. |
| `guardiansEnabled` | boolean | - | Whether or not guardian notifications are enabled for this course. Read-only. |
| `alternateLink` | string | - | Absolute link to this course in the Classroom web UI. Read-only. |
| `teacherGroupEmail` | string | - | The email address of a Google group containing all teachers of the course. This group does not accept email and can only be used for permissions. Read-only. |
| `enrollmentCode` | string | - | Enrollment code to use when joining this course. Specifying this field in a course update mask results in an error. Read-only. |
| `ownerId` | string | - | The identifier of the owner of a course. When specified as a parameter of a create course request, this field is required. The identifier can be one of the following: * the numeric identifier for the user * the email address of the user * the string literal `"me"`, indicating the requesting user ... |
| `courseMaterialSets` | Array of [`CourseMaterialSet`](#coursematerialset) | - | Sets of materials that appear on the "about" page of this course. Read-only. |
| `courseState` | string | `COURSE_STATE_UNSPECIFIED`, `ACTIVE`, `ARCHIVED`, `PROVISIONED`, `DECLINED`, `SUSPENDED` | State of the course. If unspecified, the default state is `PROVISIONED`. |
| `description` | string | - | Optional description. For example, "We'll be learning about the structure of living creatures from a combination of textbooks, guest lectures, and lab work. Expect to be excited!" If set, this field must be a valid UTF-8 string and no longer than 30,000 characters. |
| `subject` | string | - | Optional. The subject of the course. |
| `teacherFolder` | [`DriveFolder`](#drivefolder) | - | Information about a Drive Folder that is shared with all teachers of the course. This field will only be set for teachers of the course and domain administrators. Read-only. |
| `descriptionHeading` | string | - | Optional heading for the description. For example, "Welcome to 10th Grade Biology." If set, this field must be a valid UTF-8 string and no longer than 3600 characters. |
| `section` | string | - | Section of the course. For example, "Period 2". If set, this field must be a valid UTF-8 string and no longer than 2800 characters. |
| `creationTime` | string | google-datetime | Creation time of the course. Specifying this field in a course update mask results in an error. Read-only. |
| `courseGroupEmail` | string | - | The email address of a Google group containing all members of the course. This group does not accept email and can only be used for permissions. Read-only. |
| `gradebookSettings` | [`GradebookSettings`](#gradebooksettings) | - | The gradebook settings that specify how a student's overall grade for the course will be calculated and who it will be displayed to. Read-only. |
| `room` | string | - | Optional room location. For example, "301". If set, this field must be a valid UTF-8 string and no longer than 650 characters. |
| `updateTime` | string | google-datetime | Time of the most recent update to this course. Specifying this field in a course update mask results in an error. Read-only. |
| `calendarId` | string | - | The Calendar ID for a calendar that all course members can see, to which Classroom adds events for course work and announcements in the course. The Calendar for a course is created asynchronously when the course is set to `CourseState.ACTIVE` for the first time (at creation time or when it is upd... |
| `levels` | string | - | Optional. Levels for the course. Examples: "9th grade", "Middle school", "4th - 5th", "K-2", "3000". If set, this field must be a valid UTF-8 string and fewer than 1000 characters. This field can only be cleared using the `PatchCourse` method. |


---

## CourseAlias
**Type:** `object`

Alternative identifier for a course. An alias uniquely identifies a course. It must be unique within one of the following scopes: * domain: A domain-scoped alias is visible to all users within the alias creator's domain and can be created only by a domain admin. A domain-scoped alias is often used when a course has an identifier external to Classroom. * project: A project-scoped alias is visible to any request from an application using the Developer Console project ID that created the alias and can be created by any project. A project-scoped alias is often used when an application has alternative identifiers. A random value can also be used to avoid duplicate courses in the event of transmission failures, as retrying a request will return `ALREADY_EXISTS` if a previous one has succeeded.

| Field | Type | Format / Enum | Description |
|---|---|---|---|
| `alias` | string | - | Alias string. The format of the string indicates the desired alias scoping. * `d:` indicates a domain-scoped alias. Example: `d:math_101` * `p:` indicates a project-scoped alias. Example: `p:abc123` This field has a maximum length of 256 characters. |


---

## CourseMaterial
**Type:** `object`

A material attached to a course as part of a material set.

| Field | Type | Format / Enum | Description |
|---|---|---|---|
| `form` | [`Form`](#form) | - | Google Forms attachment. |
| `driveFile` | [`DriveFile`](#drivefile) | - | Google Drive file attachment. |
| `link` | [`Link`](#link) | - | Link atatchment. |
| `youTubeVideo` | [`YouTubeVideo`](#youtubevideo) | - | Youtube video attachment. |


---

## CourseMaterialSet
**Type:** `object`

A set of materials that appears on the "About" page of the course. These materials might include a syllabus, schedule, or other background information relating to the course as a whole.

| Field | Type | Format / Enum | Description |
|---|---|---|---|
| `title` | string | - | Title for this set. |
| `materials` | Array of [`CourseMaterial`](#coursematerial) | - | Materials attached to this set. |


---

## CourseRosterChangesInfo
**Type:** `object`

Information about a `Feed` with a `feed_type` of `COURSE_ROSTER_CHANGES`.

| Field | Type | Format / Enum | Description |
|---|---|---|---|
| `courseId` | string | - | The `course_id` of the course to subscribe to roster changes for. |


---

## CourseWork
**Type:** `object`

Course work created by a teacher for students of the course.

| Field | Type | Format / Enum | Description |
|---|---|---|---|
| `submissionModificationMode` | string | `SUBMISSION_MODIFICATION_MODE_UNSPECIFIED`, `MODIFIABLE_UNTIL_TURNED_IN`, `MODIFIABLE` | Setting to determine when students are allowed to modify submissions. If unspecified, the default value is `MODIFIABLE_UNTIL_TURNED_IN`. |
| `creationTime` | string | google-datetime | Timestamp when this course work was created. Read-only. |
| `dueDate` | [`Date`](#date) | - | Optional date, in UTC, that submissions for this course work are due. This must be specified if `due_time` is specified. |
| `updateTime` | string | google-datetime | Timestamp of the most recent change to this course work. Read-only. |
| `dueTime` | [`TimeOfDay`](#timeofday) | - | Optional time of day, in UTC, that submissions for this course work are due. This must be specified if `due_date` is specified. |
| `assignment` | [`Assignment`](#assignment) | - | Assignment details. This is populated only when `work_type` is `ASSIGNMENT`. Read-only. |
| `gradeCategory` | [`GradeCategory`](#gradecategory) | - | The category that this coursework's grade contributes to. Present only when a category has been chosen for the coursework. May be used in calculating the overall grade. Read-only. |
| `alternateLink` | string | - | Absolute link to this course work in the Classroom web UI. This is only populated if `state` is `PUBLISHED`. Read-only. |
| `multipleChoiceQuestion` | [`MultipleChoiceQuestion`](#multiplechoicequestion) | - | Multiple choice question details. For read operations, this field is populated only when `work_type` is `MULTIPLE_CHOICE_QUESTION`. For write operations, this field must be specified when creating course work with a `work_type` of `MULTIPLE_CHOICE_QUESTION`, and it must not be set otherwise. |
| `creatorUserId` | string | - | Identifier for the user that created the coursework. Read-only. |
| `associatedWithDeveloper` | boolean | - | Whether this course work item is associated with the Developer Console project making the request. See CreateCourseWork for more details. Read-only. |
| `state` | string | `COURSE_WORK_STATE_UNSPECIFIED`, `PUBLISHED`, `DRAFT`, `DELETED` | Status of this course work. If unspecified, the default state is `DRAFT`. |
| `scheduledTime` | string | google-datetime | Optional timestamp when this course work is scheduled to be published. |
| `topicId` | string | - | Identifier for the topic that this coursework is associated with. Must match an existing topic in the course. |
| `maxPoints` | number | double | Maximum grade for this course work. If zero or unspecified, this assignment is considered ungraded. This must be a non-negative integer value. |
| `assigneeMode` | string | `ASSIGNEE_MODE_UNSPECIFIED`, `ALL_STUDENTS`, `INDIVIDUAL_STUDENTS` | Assignee mode of the coursework. If unspecified, the default value is `ALL_STUDENTS`. |
| `description` | string | - | Optional description of this course work. If set, the description must be a valid UTF-8 string containing no more than 30,000 characters. |
| `courseId` | string | - | Identifier of the course. Read-only. |
| `materials` | Array of [`Material`](#material) | - | Additional materials. CourseWork must have no more than 20 material items. |
| `individualStudentsOptions` | [`IndividualStudentsOptions`](#individualstudentsoptions) | - | Identifiers of students with access to the coursework. This field is set only if `assigneeMode` is `INDIVIDUAL_STUDENTS`. If the `assigneeMode` is `INDIVIDUAL_STUDENTS`, then only students specified in this field are assigned the coursework. |
| `id` | string | - | Classroom-assigned identifier of this course work, unique per course. Read-only. |
| `gradingPeriodId` | string | - | Identifier of the grading period associated with the coursework. * At creation, if unspecified, the grading period ID will be set based on the `dueDate` (or `scheduledTime` if no `dueDate` is set). * To indicate no association to any grading period, set this field to an empty string (""). * If sp... |
| `title` | string | - | Title of this course work. The title must be a valid UTF-8 string containing between 1 and 3000 characters. |
| `workType` | string | `COURSE_WORK_TYPE_UNSPECIFIED`, `ASSIGNMENT`, `SHORT_ANSWER_QUESTION`, `MULTIPLE_CHOICE_QUESTION` | Type of this course work. The type is set when the course work is created and cannot be changed. |


---

## CourseWorkChangesInfo
**Type:** `object`

Information about a `Feed` with a `feed_type` of `COURSE_WORK_CHANGES`.

| Field | Type | Format / Enum | Description |
|---|---|---|---|
| `courseId` | string | - | The `course_id` of the course to subscribe to work changes for. |


---

## CourseWorkMaterial
**Type:** `object`

Course work material created by a teacher for students of the course

| Field | Type | Format / Enum | Description |
|---|---|---|---|
| `topicId` | string | - | Identifier for the topic that this course work material is associated with. Must match an existing topic in the course. |
| `state` | string | `COURSEWORK_MATERIAL_STATE_UNSPECIFIED`, `PUBLISHED`, `DRAFT`, `DELETED` | Status of this course work material. If unspecified, the default state is `DRAFT`. |
| `description` | string | - | Optional description of this course work material. The text must be a valid UTF-8 string containing no more than 30,000 characters. |
| `id` | string | - | Classroom-assigned identifier of this course work material, unique per course. Read-only. |
| `individualStudentsOptions` | [`IndividualStudentsOptions`](#individualstudentsoptions) | - | Identifiers of students with access to the course work material. This field is set only if `assigneeMode` is `INDIVIDUAL_STUDENTS`. If the `assigneeMode` is `INDIVIDUAL_STUDENTS`, then only students specified in this field can see the course work material. |
| `creationTime` | string | google-datetime | Timestamp when this course work material was created. Read-only. |
| `scheduledTime` | string | google-datetime | Optional timestamp when this course work material is scheduled to be published. |
| `courseId` | string | - | Identifier of the course. Read-only. |
| `title` | string | - | Title of this course work material. The title must be a valid UTF-8 string containing between 1 and 3000 characters. |
| `materials` | Array of [`Material`](#material) | - | Additional materials. A course work material must have no more than 20 material items. |
| `creatorUserId` | string | - | Identifier for the user that created the course work material. Read-only. |
| `assigneeMode` | string | `ASSIGNEE_MODE_UNSPECIFIED`, `ALL_STUDENTS`, `INDIVIDUAL_STUDENTS` | Assignee mode of the course work material. If unspecified, the default value is `ALL_STUDENTS`. |
| `alternateLink` | string | - | Absolute link to this course work material in the Classroom web UI. This is only populated if `state` is `PUBLISHED`. Read-only. |
| `updateTime` | string | google-datetime | Timestamp of the most recent change to this course work material. Read-only. |


---

## Criterion
**Type:** `object`

A rubric criterion. Each criterion is a dimension on which performance is rated.

| Field | Type | Format / Enum | Description |
|---|---|---|---|
| `levels` | Array of [`Level`](#level) | - | The list of levels within this criterion. |
| `id` | string | - | The criterion ID. On creation, an ID is assigned. |
| `description` | string | - | The description of the criterion. |
| `title` | string | - | The title of the criterion. |


---

## Date
**Type:** `object`

Represents a whole or partial calendar date, such as a birthday. The time of day and time zone are either specified elsewhere or are insignificant. The date is relative to the Gregorian Calendar. This can represent one of the following: * A full date, with non-zero year, month, and day values. * A month and day, with a zero year (for example, an anniversary). * A year on its own, with a zero month and a zero day. * A year and month, with a zero day (for example, a credit card expiration date). Related types: * google.type.TimeOfDay * google.type.DateTime * google.protobuf.Timestamp

| Field | Type | Format / Enum | Description |
|---|---|---|---|
| `month` | integer | int32 | Month of a year. Must be from 1 to 12, or 0 to specify a year without a month and day. |
| `year` | integer | int32 | Year of the date. Must be from 1 to 9999, or 0 to specify a date without a year. |
| `day` | integer | int32 | Day of a month. Must be from 1 to 31 and valid for the year and month, or 0 to specify a year by itself or a year and month where the day isn't significant. |


---

## DriveFile
**Type:** `object`

Representation of a Google Drive file.

| Field | Type | Format / Enum | Description |
|---|---|---|---|
| `thumbnailUrl` | string | - | URL of a thumbnail image of the Drive item. Read-only. |
| `id` | string | - | Drive API resource ID. |
| `alternateLink` | string | - | URL that can be used to access the Drive item. Read-only. |
| `title` | string | - | Title of the Drive item. Read-only. |


---

## DriveFolder
**Type:** `object`

Representation of a Google Drive folder.

| Field | Type | Format / Enum | Description |
|---|---|---|---|
| `alternateLink` | string | - | URL that can be used to access the Drive folder. Read-only. |
| `id` | string | - | Drive API resource ID. |
| `title` | string | - | Title of the Drive folder. Read-only. |


---

## EmbedUri
**Type:** `object`

URI to be iframed after being populated with query parameters.

| Field | Type | Format / Enum | Description |
|---|---|---|---|
| `uri` | string | - | Required. URI to be iframed after being populated with query parameters. This must be a valid UTF-8 string containing between 1 and 1800 characters. |


---

## Empty
**Type:** `object`

A generic empty message that you can re-use to avoid defining duplicated empty messages in your APIs. A typical example is to use it as the request or the response type of an API method. For instance: service Foo { rpc Bar(google.protobuf.Empty) returns (google.protobuf.Empty); }


---

## Feed
**Type:** `object`

A class of notifications that an application can register to receive. For example: "all roster changes for a domain".

| Field | Type | Format / Enum | Description |
|---|---|---|---|
| `courseRosterChangesInfo` | [`CourseRosterChangesInfo`](#courserosterchangesinfo) | - | Information about a `Feed` with a `feed_type` of `COURSE_ROSTER_CHANGES`. This field must be specified if `feed_type` is `COURSE_ROSTER_CHANGES`. |
| `courseWorkChangesInfo` | [`CourseWorkChangesInfo`](#courseworkchangesinfo) | - | Information about a `Feed` with a `feed_type` of `COURSE_WORK_CHANGES`. This field must be specified if `feed_type` is `COURSE_WORK_CHANGES`. |
| `feedType` | string | `FEED_TYPE_UNSPECIFIED`, `DOMAIN_ROSTER_CHANGES`, `COURSE_ROSTER_CHANGES`, `COURSE_WORK_CHANGES` | The type of feed. |


---

## Form
**Type:** `object`

Google Forms item.

| Field | Type | Format / Enum | Description |
|---|---|---|---|
| `responseUrl` | string | - | URL of the form responses document. Only set if responses have been recorded and only when the requesting user is an editor of the form. Read-only. |
| `title` | string | - | Title of the Form. Read-only. |
| `formUrl` | string | - | URL of the form. |
| `thumbnailUrl` | string | - | URL of a thumbnail image of the Form. Read-only. |


---

## GeminiGem
**Type:** `object`

Gemini Gem link.

| Field | Type | Format / Enum | Description |
|---|---|---|---|
| `id` | string | - | Gems resource id. |
| `url` | string | - | URL that can be used to access the Gem. |
| `title` | string | - | Title of the Gem. |


---

## GlobalPermission
**Type:** `object`

Global user permission description.

| Field | Type | Format / Enum | Description |
|---|---|---|---|
| `permission` | string | `PERMISSION_UNSPECIFIED`, `CREATE_COURSE` | Permission value. |


---

## GradeCategory
**Type:** `object`

Details for a grade category in a course. Coursework may have zero or one grade category, and the category may be used in computing the overall grade. See the [help center article](https://support.google.com/edu/classroom/answer/9184995) for details.

| Field | Type | Format / Enum | Description |
|---|---|---|---|
| `name` | string | - | Name of the grade category. |
| `id` | string | - | ID of the grade category. |
| `defaultGradeDenominator` | integer | int32 | Default value of denominator. Only applicable when grade calculation type is TOTAL_POINTS. |
| `weight` | integer | int32 | The weight of the category average as part of overall average. A weight of 12.34% is represented as 123400 (100% is 1,000,000). The last two digits should always be zero since we use two decimal precision. Only applicable when grade calculation type is WEIGHTED_CATEGORIES. |


---

## GradeHistory
**Type:** `object`

The history of each grade on this submission.

| Field | Type | Format / Enum | Description |
|---|---|---|---|
| `gradeTimestamp` | string | google-datetime | When the grade of the submission was changed. |
| `actorUserId` | string | - | The teacher who made the grade change. |
| `maxPoints` | number | double | The denominator of the grade at this time in the submission grade history. |
| `gradeChangeType` | string | `UNKNOWN_GRADE_CHANGE_TYPE`, `DRAFT_GRADE_POINTS_EARNED_CHANGE`, `ASSIGNED_GRADE_POINTS_EARNED_CHANGE`, `MAX_POINTS_CHANGE` | The type of grade change at this time in the submission grade history. |
| `pointsEarned` | number | double | The numerator of the grade at this time in the submission grade history. |


---

## GradebookSettings
**Type:** `object`

The gradebook settings for a course. See the [help center article](https://support.google.com/edu/classroom/answer/9184995) for details.

| Field | Type | Format / Enum | Description |
|---|---|---|---|
| `calculationType` | string | `CALCULATION_TYPE_UNSPECIFIED`, `TOTAL_POINTS`, `WEIGHTED_CATEGORIES` | Indicates how the overall grade is calculated. |
| `gradeCategories` | Array of [`GradeCategory`](#gradecategory) | - | Grade categories that are available for coursework in the course. |
| `displaySetting` | string | `DISPLAY_SETTING_UNSPECIFIED`, `SHOW_OVERALL_GRADE`, `HIDE_OVERALL_GRADE`, `SHOW_TEACHERS_ONLY` | Indicates who can see the overall grade.. |


---

## GradingPeriod
**Type:** `object`

An individual grading period. Grading periods must not have overlapping date ranges and must be listed in chronological order. For example, if the end_date of a grading period is 2024-01-25, then the start_date of the next grading period must be 2024-01-26 or later. Each grading period must have a unique title within a course.

| Field | Type | Format / Enum | Description |
|---|---|---|---|
| `id` | string | - | Output only. System generated grading period ID. Read-only. |
| `startDate` | [`Date`](#date) | - | Required. Start date, in UTC, of the grading period. Inclusive. |
| `endDate` | [`Date`](#date) | - | Required. End date, in UTC, of the grading period. Inclusive. |
| `title` | string | - | Required. Title of the grading period. For example, “Semester 1”. |


---

## GradingPeriodSettings
**Type:** `object`

Grading period settings that include all the individual grading periods in a course.

| Field | Type | Format / Enum | Description |
|---|---|---|---|
| `gradingPeriods` | Array of [`GradingPeriod`](#gradingperiod) | - | The list of grading periods in a specific course. Grading periods must not have overlapping date ranges and must be listed in chronological order. Each grading period must have a unique title within a course. |
| `applyToExistingCoursework` | boolean | - | Supports toggling the application of grading periods on existing stream items. Once set, this value is persisted meaning that it does not need to be set in every request to update `GradingPeriodSettings`. If not previously set, the default is False. |


---

## Guardian
**Type:** `object`

Association between a student and a guardian of that student. The guardian may receive information about the student's course work.

| Field | Type | Format / Enum | Description |
|---|---|---|---|
| `invitedEmailAddress` | string | - | The email address to which the initial guardian invitation was sent. This field is only visible to domain administrators. |
| `guardianId` | string | - | Identifier for the guardian. |
| `guardianProfile` | [`UserProfile`](#userprofile) | - | User profile for the guardian. |
| `studentId` | string | - | Identifier for the student to whom the guardian relationship applies. |


---

## GuardianInvitation
**Type:** `object`

An invitation to become the guardian of a specified user, sent to a specified email address.

| Field | Type | Format / Enum | Description |
|---|---|---|---|
| `state` | string | `GUARDIAN_INVITATION_STATE_UNSPECIFIED`, `PENDING`, `COMPLETE` | The state that this invitation is in. |
| `invitedEmailAddress` | string | - | Email address that the invitation was sent to. This field is only visible to domain administrators. |
| `studentId` | string | - | ID of the student (in standard format) |
| `creationTime` | string | google-datetime | The time that this invitation was created. Read-only. |
| `invitationId` | string | - | Unique identifier for this invitation. Read-only. |


---

## IndividualStudentsOptions
**Type:** `object`

Assignee details about a coursework/announcement. This field is set if and only if `assigneeMode` is `INDIVIDUAL_STUDENTS`.

| Field | Type | Format / Enum | Description |
|---|---|---|---|
| `studentIds` | Array of `string` | - | Identifiers for the students that have access to the coursework/announcement. |


---

## Invitation
**Type:** `object`

An invitation to join a course.

| Field | Type | Format / Enum | Description |
|---|---|---|---|
| `id` | string | - | Identifier assigned by Classroom. Read-only. |
| `userId` | string | - | Identifier of the invited user. When specified as a parameter of a request, this identifier can be set to one of the following: * the numeric identifier for the user * the email address of the user * the string literal `"me"`, indicating the requesting user |
| `role` | string | `COURSE_ROLE_UNSPECIFIED`, `STUDENT`, `TEACHER`, `OWNER` | Role to invite the user to have. Must not be `COURSE_ROLE_UNSPECIFIED`. |
| `courseId` | string | - | Identifier of the course to invite the user to. |


---

## Level
**Type:** `object`

A level of the criterion.

| Field | Type | Format / Enum | Description |
|---|---|---|---|
| `points` | number | double | Optional points associated with this level. If set, all levels within the rubric must specify points and the value must be distinct across all levels within a single criterion. 0 is distinct from no points. |
| `id` | string | - | The level ID. On creation, an ID is assigned. |
| `title` | string | - | The title of the level. If the level has no points set, title must be set. |
| `description` | string | - | The description of the level. |


---

## Link
**Type:** `object`

URL item.

| Field | Type | Format / Enum | Description |
|---|---|---|---|
| `thumbnailUrl` | string | - | URL of a thumbnail image of the target URL. Read-only. |
| `title` | string | - | Title of the target of the URL. Read-only. |
| `url` | string | - | URL to link to. This must be a valid UTF-8 string containing between 1 and 2024 characters. |


---

## ListAddOnAttachmentStudentSubmissionsResponse
**Type:** `object`

Response when listing student submissions for an add-on attachment.

| Field | Type | Format / Enum | Description |
|---|---|---|---|
| `addOnAttachmentStudentSubmissions` | Array of [`AddOnAttachmentStudentSubmission`](#addonattachmentstudentsubmission) | - | Add-on attachment student submissions that match the request. |
| `nextPageToken` | string | - | A token, which can be sent as `pageToken` to retrieve the next page. If this field is omitted, there are no subsequent pages. |


---

## ListAddOnAttachmentsResponse
**Type:** `object`

Response when listing add-on attachments.

| Field | Type | Format / Enum | Description |
|---|---|---|---|
| `addOnAttachments` | Array of [`AddOnAttachment`](#addonattachment) | - | Attachments under the given post. |
| `nextPageToken` | string | - | A token, which can be sent as `pageToken` to retrieve the next page. If this field is omitted, there are no subsequent pages. |


---

## ListAnnouncementsResponse
**Type:** `object`

Response when listing course work.

| Field | Type | Format / Enum | Description |
|---|---|---|---|
| `nextPageToken` | string | - | Token identifying the next page of results to return. If empty, no further results are available. |
| `announcements` | Array of [`Announcement`](#announcement) | - | Announcement items that match the request. |


---

## ListCourseAliasesResponse
**Type:** `object`

Response when listing course aliases.

| Field | Type | Format / Enum | Description |
|---|---|---|---|
| `nextPageToken` | string | - | Token identifying the next page of results to return. If empty, no further results are available. |
| `aliases` | Array of [`CourseAlias`](#coursealias) | - | The course aliases. |


---

## ListCourseWorkMaterialResponse
**Type:** `object`

Response when listing course work material.

| Field | Type | Format / Enum | Description |
|---|---|---|---|
| `nextPageToken` | string | - | Token identifying the next page of results to return. If empty, no further results are available. |
| `courseWorkMaterial` | Array of [`CourseWorkMaterial`](#courseworkmaterial) | - | Course work material items that match the request. |


---

## ListCourseWorkResponse
**Type:** `object`

Response when listing course work.

| Field | Type | Format / Enum | Description |
|---|---|---|---|
| `nextPageToken` | string | - | Token identifying the next page of results to return. If empty, no further results are available. |
| `courseWork` | Array of [`CourseWork`](#coursework) | - | Course work items that match the request. |


---

## ListCoursesResponse
**Type:** `object`

Response when listing courses.

| Field | Type | Format / Enum | Description |
|---|---|---|---|
| `courses` | Array of [`Course`](#course) | - | Courses that match the list request. |
| `nextPageToken` | string | - | Token identifying the next page of results to return. If empty, no further results are available. |


---

## ListGuardianInvitationsResponse
**Type:** `object`

Response when listing guardian invitations.

| Field | Type | Format / Enum | Description |
|---|---|---|---|
| `guardianInvitations` | Array of [`GuardianInvitation`](#guardianinvitation) | - | Guardian invitations that matched the list request. |
| `nextPageToken` | string | - | Token identifying the next page of results to return. If empty, no further results are available. |


---

## ListGuardiansResponse
**Type:** `object`

Response when listing guardians.

| Field | Type | Format / Enum | Description |
|---|---|---|---|
| `guardians` | Array of [`Guardian`](#guardian) | - | Guardians on this page of results that met the criteria specified in the request. |
| `nextPageToken` | string | - | Token identifying the next page of results to return. If empty, no further results are available. |


---

## ListInvitationsResponse
**Type:** `object`

Response when listing invitations.

| Field | Type | Format / Enum | Description |
|---|---|---|---|
| `invitations` | Array of [`Invitation`](#invitation) | - | Invitations that match the list request. |
| `nextPageToken` | string | - | Token identifying the next page of results to return. If empty, no further results are available. |


---

## ListRubricsResponse
**Type:** `object`

Response when listing rubrics.

| Field | Type | Format / Enum | Description |
|---|---|---|---|
| `nextPageToken` | string | - | Token identifying the next page of results to return. If empty, no further results are available. |
| `rubrics` | Array of [`Rubric`](#rubric) | - | Rubrics that match the request. |


---

## ListStudentGroupMembersResponse
**Type:** `object`

Response when listing students in a group.

| Field | Type | Format / Enum | Description |
|---|---|---|---|
| `studentGroupMembers` | Array of [`StudentGroupMember`](#studentgroupmember) | - | The student group members. |
| `nextPageToken` | string | - | Token identifying the next page of results to return. If empty, no further results are available. |


---

## ListStudentGroupsResponse
**Type:** `object`

Response when listing student groups.

| Field | Type | Format / Enum | Description |
|---|---|---|---|
| `studentGroups` | Array of [`StudentGroup`](#studentgroup) | - | The student groups. |
| `nextPageToken` | string | - | Token identifying the next page of results to return. If empty, no further results are available. |


---

## ListStudentSubmissionsResponse
**Type:** `object`

Response when listing student submissions.

| Field | Type | Format / Enum | Description |
|---|---|---|---|
| `nextPageToken` | string | - | Token identifying the next page of results to return. If empty, no further results are available. |
| `studentSubmissions` | Array of [`StudentSubmission`](#studentsubmission) | - | Student work that matches the request. |


---

## ListStudentsResponse
**Type:** `object`

Response when listing students.

| Field | Type | Format / Enum | Description |
|---|---|---|---|
| `students` | Array of [`Student`](#student) | - | Students who match the list request. |
| `nextPageToken` | string | - | Token identifying the next page of results to return. If empty, no further results are available. |


---

## ListTeachersResponse
**Type:** `object`

Response when listing teachers.

| Field | Type | Format / Enum | Description |
|---|---|---|---|
| `nextPageToken` | string | - | Token identifying the next page of results to return. If empty, no further results are available. |
| `teachers` | Array of [`Teacher`](#teacher) | - | Teachers who match the list request. |


---

## ListTopicResponse
**Type:** `object`

Response when listing topics.

| Field | Type | Format / Enum | Description |
|---|---|---|---|
| `nextPageToken` | string | - | Token identifying the next page of results to return. If empty, no further results are available. |
| `topic` | Array of [`Topic`](#topic) | - | Topic items that match the request. |


---

## Material
**Type:** `object`

Material attached to course work. When creating attachments, setting the `form`, `gem`, or `notebook` field is not supported.

| Field | Type | Format / Enum | Description |
|---|---|---|---|
| `form` | [`Form`](#form) | - | Google Forms material. Read-only. |
| `driveFile` | [`SharedDriveFile`](#shareddrivefile) | - | Google Drive file material. |
| `gem` | [`GeminiGem`](#geminigem) | - | Gemini Gem material. Read-only. |
| `youtubeVideo` | [`YouTubeVideo`](#youtubevideo) | - | YouTube video material. |
| `link` | [`Link`](#link) | - | Link material. On creation, this is upgraded to a more appropriate type if possible, and this is reflected in the response. |
| `notebook` | [`NotebookLmNotebook`](#notebooklmnotebook) | - | NotebookLM Notebook material. Read-only. |


---

## ModifyAnnouncementAssigneesRequest
**Type:** `object`

Request to modify assignee mode and options of an announcement.

| Field | Type | Format / Enum | Description |
|---|---|---|---|
| `modifyIndividualStudentsOptions` | [`ModifyIndividualStudentsOptions`](#modifyindividualstudentsoptions) | - | Set which students can view or cannot view the announcement. Must be specified only when `assigneeMode` is `INDIVIDUAL_STUDENTS`. |
| `assigneeMode` | string | `ASSIGNEE_MODE_UNSPECIFIED`, `ALL_STUDENTS`, `INDIVIDUAL_STUDENTS` | Mode of the announcement describing whether it is accessible by all students or specified individual students. |


---

## ModifyAttachmentsRequest
**Type:** `object`

Request to modify the attachments of a student submission.

| Field | Type | Format / Enum | Description |
|---|---|---|---|
| `addAttachments` | Array of [`Attachment`](#attachment) | - | Attachments to add. A student submission may not have more than 20 attachments. Form attachments are not supported. |


---

## ModifyCourseWorkAssigneesRequest
**Type:** `object`

Request to modify assignee mode and options of a coursework.

| Field | Type | Format / Enum | Description |
|---|---|---|---|
| `modifyIndividualStudentsOptions` | [`ModifyIndividualStudentsOptions`](#modifyindividualstudentsoptions) | - | Set which students are assigned or not assigned to the coursework. Must be specified only when `assigneeMode` is `INDIVIDUAL_STUDENTS`. |
| `assigneeMode` | string | `ASSIGNEE_MODE_UNSPECIFIED`, `ALL_STUDENTS`, `INDIVIDUAL_STUDENTS` | Mode of the coursework describing whether it will be assigned to all students or specified individual students. |


---

## ModifyIndividualStudentsOptions
**Type:** `object`

Contains fields to add or remove students from a course work or announcement where the `assigneeMode` is set to `INDIVIDUAL_STUDENTS`.

| Field | Type | Format / Enum | Description |
|---|---|---|---|
| `addStudentIds` | Array of `string` | - | IDs of students to be added as having access to this coursework/announcement. |
| `removeStudentIds` | Array of `string` | - | IDs of students to be removed from having access to this coursework/announcement. |


---

## MultipleChoiceQuestion
**Type:** `object`

Additional details for multiple-choice questions.

| Field | Type | Format / Enum | Description |
|---|---|---|---|
| `choices` | Array of `string` | - | Possible choices. |


---

## MultipleChoiceSubmission
**Type:** `object`

Student work for a multiple-choice question.

| Field | Type | Format / Enum | Description |
|---|---|---|---|
| `answer` | string | - | Student's select choice. |


---

## Name
**Type:** `object`

Details of the user's name.

| Field | Type | Format / Enum | Description |
|---|---|---|---|
| `familyName` | string | - | The user's last name. Read-only. |
| `fullName` | string | - | The user's full name formed by concatenating the first and last name values. Read-only. |
| `givenName` | string | - | The user's first name. Read-only. |


---

## NotebookLmNotebook
**Type:** `object`

NotebookLM Notebook link.

| Field | Type | Format / Enum | Description |
|---|---|---|---|
| `title` | string | - | Title of the Notebook. |
| `id` | string | - | Notebook resource id. |
| `url` | string | - | URL that can be used to access the Notebook. |


---

## ReclaimStudentSubmissionRequest
**Type:** `object`

Request to reclaim a student submission.


---

## Registration
**Type:** `object`

An instruction to Classroom to send notifications from the `feed` to the provided destination.

| Field | Type | Format / Enum | Description |
|---|---|---|---|
| `cloudPubsubTopic` | [`CloudPubsubTopic`](#cloudpubsubtopic) | - | The Cloud Pub/Sub topic that notifications are to be sent to. |
| `expiryTime` | string | google-datetime | The time until which the `Registration` is effective. This is a read-only field assigned by the server. |
| `registrationId` | string | - | A server-generated unique identifier for this `Registration`. Read-only. |
| `feed` | [`Feed`](#feed) | - | Specification for the class of notifications that Classroom should deliver to the destination. |


---

## ReturnStudentSubmissionRequest
**Type:** `object`

Request to return a student submission.


---

## Rubric
**Type:** `object`

The rubric of the course work. A rubric is a scoring guide used to evaluate student work and give feedback. For further details, see [Rubrics structure and known limitations](/classroom/rubrics/limitations).

| Field | Type | Format / Enum | Description |
|---|---|---|---|
| `courseId` | string | - | Identifier of the course. Read-only. |
| `sourceSpreadsheetId` | string | - | Input only. Immutable. Google Sheets ID of the spreadsheet. This spreadsheet must contain formatted rubric settings. See [Create or reuse a rubric for an assignment](https://support.google.com/edu/classroom/answer/9335069). Use of this field requires the `https://www.googleapis.com/auth/spreadshe... |
| `updateTime` | string | google-datetime | Output only. Timestamp of the most recent change to this rubric. Read-only. |
| `courseWorkId` | string | - | Identifier for the course work this corresponds to. Read-only. |
| `creationTime` | string | google-datetime | Output only. Timestamp when this rubric was created. Read-only. |
| `id` | string | - | Classroom-assigned identifier for the rubric. This is unique among rubrics for the relevant course work. Read-only. |
| `criteria` | Array of [`Criterion`](#criterion) | - | List of criteria. Each criterion is a dimension on which performance is rated. |


---

## RubricGrade
**Type:** `object`

A rubric grade set for the student submission. There is at most one entry per rubric criterion.

| Field | Type | Format / Enum | Description |
|---|---|---|---|
| `levelId` | string | - | Optional. Optional level ID of the selected level. If empty, no level was selected. |
| `criterionId` | string | - | Optional. Criterion ID. |
| `points` | number | double | Optional. Optional points assigned for this criterion, typically based on the level. Levels might or might not have points. If unset, no points were set for this criterion. |


---

## SharedDriveFile
**Type:** `object`

Drive file that is used as material for course work.

| Field | Type | Format / Enum | Description |
|---|---|---|---|
| `shareMode` | string | `UNKNOWN_SHARE_MODE`, `VIEW`, `EDIT`, `STUDENT_COPY` | Mechanism by which students access the Drive item. |
| `driveFile` | [`DriveFile`](#drivefile) | - | Drive file details. |


---

## ShortAnswerSubmission
**Type:** `object`

Student work for a short answer question.

| Field | Type | Format / Enum | Description |
|---|---|---|---|
| `answer` | string | - | Student response to a short-answer question. |


---

## StateHistory
**Type:** `object`

The history of each state this submission has been in.

| Field | Type | Format / Enum | Description |
|---|---|---|---|
| `actorUserId` | string | - | The teacher or student who made the change. |
| `state` | string | `STATE_UNSPECIFIED`, `CREATED`, `TURNED_IN`, `RETURNED`, `RECLAIMED_BY_STUDENT`, `STUDENT_EDITED_AFTER_TURN_IN` | The workflow pipeline stage. |
| `stateTimestamp` | string | google-datetime | When the submission entered this state. |


---

## Student
**Type:** `object`

Student in a course.

| Field | Type | Format / Enum | Description |
|---|---|---|---|
| `profile` | [`UserProfile`](#userprofile) | - | Global user information for the student. Read-only. |
| `userId` | string | - | Identifier of the user. When specified as a parameter of a request, this identifier can be one of the following: * the numeric identifier for the user * the email address of the user * the string literal `"me"`, indicating the requesting user |
| `studentWorkFolder` | [`DriveFolder`](#drivefolder) | - | Information about a Drive Folder for this student's work in this course. Only visible to the student and domain administrators. Read-only. |
| `courseId` | string | - | Identifier of the course. Read-only. |


---

## StudentContext
**Type:** `object`

Role-specific context if the requesting user is a student.

| Field | Type | Format / Enum | Description |
|---|---|---|---|
| `submissionId` | string | - | Requesting user's submission id to be used for grade passback and to identify the student when showing student work to the teacher. This is set exactly when `supportsStudentWork` is `true`. |


---

## StudentGroup
**Type:** `object`

A student group in a course.

| Field | Type | Format / Enum | Description |
|---|---|---|---|
| `id` | string | - | The identifier of the student group. |
| `courseId` | string | - | The identifier of the course. |
| `title` | string | - | The title of the student group. |


---

## StudentGroupMember
**Type:** `object`

A student member in a student group.

| Field | Type | Format / Enum | Description |
|---|---|---|---|
| `studentGroupId` | string | - | The identifier of the student group. |
| `userId` | string | - | Identifier of the student. |
| `courseId` | string | - | The identifier of the course. |


---

## StudentSubmission
**Type:** `object`

Student submission for course work. `StudentSubmission` items are generated when a `CourseWork` item is created. Student submissions that have never been accessed (i.e. with `state` = NEW) may not have a creation time or update time.

| Field | Type | Format / Enum | Description |
|---|---|---|---|
| `draftRubricGrades` | object | - | Pending rubric grades based on the rubric's criteria. This map is empty if there is no rubric attached to this course work or if a rubric is attached, but no grades have been set on any criteria. Entries are only populated for grades that have been set. Key: The rubric's criterion ID. Read-only. |
| `alternateLink` | string | - | Absolute link to the submission in the Classroom web UI. Read-only. |
| `assignmentSubmission` | [`AssignmentSubmission`](#assignmentsubmission) | - | Submission content when course_work_type is ASSIGNMENT. Students can modify this content using ModifyAttachments. |
| `submissionHistory` | Array of [`SubmissionHistory`](#submissionhistory) | - | The history of the submission (includes state and grade histories). Read-only. |
| `courseWorkId` | string | - | Identifier for the course work this corresponds to. Read-only. |
| `state` | string | `SUBMISSION_STATE_UNSPECIFIED`, `NEW`, `CREATED`, `TURNED_IN`, `RETURNED`, `RECLAIMED_BY_STUDENT` | State of this submission. Read-only. |
| `associatedWithDeveloper` | boolean | - | Whether this student submission is associated with the Developer Console project making the request. See CreateCourseWork for more details. Read-only. |
| `late` | boolean | - | Whether this submission is late. Read-only. |
| `updateTime` | string | google-datetime | Last update time of this submission. This may be unset if the student has not accessed this item. Read-only. |
| `shortAnswerSubmission` | [`ShortAnswerSubmission`](#shortanswersubmission) | - | Submission content when course_work_type is SHORT_ANSWER_QUESTION. |
| `assignedGrade` | number | double | Optional grade. If unset, no grade was set. This value must be non-negative. Decimal (that is, non-integer) values are allowed, but are rounded to two decimal places. This may be modified only by course teachers. |
| `draftGrade` | number | double | Optional pending grade. If unset, no grade was set. This value must be non-negative. Decimal (that is, non-integer) values are allowed, but are rounded to two decimal places. This is only visible to and modifiable by course teachers. |
| `id` | string | - | Classroom-assigned Identifier for the student submission. This is unique among submissions for the relevant course work. Read-only. |
| `userId` | string | - | Identifier for the student that owns this submission. Read-only. |
| `multipleChoiceSubmission` | [`MultipleChoiceSubmission`](#multiplechoicesubmission) | - | Submission content when course_work_type is MULTIPLE_CHOICE_QUESTION. |
| `assignedRubricGrades` | object | - | Assigned rubric grades based on the rubric's Criteria. This map is empty if there is no rubric attached to this course work or if a rubric is attached, but no grades have been set on any Criteria. Entries are only populated for grades that have been set. Key: The rubric's criterion ID. Read-only. |
| `courseWorkType` | string | `COURSE_WORK_TYPE_UNSPECIFIED`, `ASSIGNMENT`, `SHORT_ANSWER_QUESTION`, `MULTIPLE_CHOICE_QUESTION` | Type of course work this submission is for. Read-only. |
| `creationTime` | string | google-datetime | Creation time of this submission. This may be unset if the student has not accessed this item. Read-only. |
| `courseId` | string | - | Identifier of the course. Read-only. |


---

## SubmissionHistory
**Type:** `object`

The history of the submission. This currently includes state and grade histories.

| Field | Type | Format / Enum | Description |
|---|---|---|---|
| `stateHistory` | [`StateHistory`](#statehistory) | - | The state history information of the submission, if present. |
| `gradeHistory` | [`GradeHistory`](#gradehistory) | - | The grade history information of the submission, if present. |


---

## Teacher
**Type:** `object`

Teacher of a course.

| Field | Type | Format / Enum | Description |
|---|---|---|---|
| `courseId` | string | - | Identifier of the course. Read-only. |
| `userId` | string | - | Identifier of the user. When specified as a parameter of a request, this identifier can be one of the following: * the numeric identifier for the user * the email address of the user * the string literal `"me"`, indicating the requesting user |
| `profile` | [`UserProfile`](#userprofile) | - | Global user information for the teacher. Read-only. |


---

## TeacherContext
**Type:** `object`

Role-specific context if the requesting user is a teacher.


---

## TimeOfDay
**Type:** `object`

Represents a time of day. The date and time zone are either not significant or are specified elsewhere. An API may choose to allow leap seconds. Related types are google.type.Date and `google.protobuf.Timestamp`.

| Field | Type | Format / Enum | Description |
|---|---|---|---|
| `seconds` | integer | int32 | Seconds of a minute. Must be greater than or equal to 0 and typically must be less than or equal to 59. An API may allow the value 60 if it allows leap-seconds. |
| `hours` | integer | int32 | Hours of a day in 24 hour format. Must be greater than or equal to 0 and typically must be less than or equal to 23. An API may choose to allow the value "24:00:00" for scenarios like business closing time. |
| `nanos` | integer | int32 | Fractions of seconds, in nanoseconds. Must be greater than or equal to 0 and less than or equal to 999,999,999. |
| `minutes` | integer | int32 | Minutes of an hour. Must be greater than or equal to 0 and less than or equal to 59. |


---

## Topic
**Type:** `object`

Topic created by a teacher for the course

| Field | Type | Format / Enum | Description |
|---|---|---|---|
| `courseId` | string | - | Identifier of the course. Read-only. |
| `updateTime` | string | google-datetime | The time the topic was last updated by the system. Read-only. |
| `topicId` | string | - | Unique identifier for the topic. Read-only. |
| `name` | string | - | The name of the topic, generated by the user. Leading and trailing whitespaces, if any, are trimmed. Also, multiple consecutive whitespaces are collapsed into one inside the name. The result must be a non-empty string. Topic names are case sensitive, and must be no longer than 100 characters. |


---

## TurnInStudentSubmissionRequest
**Type:** `object`

Request to turn in a student submission.


---

## UserProfile
**Type:** `object`

Global information for a user.

| Field | Type | Format / Enum | Description |
|---|---|---|---|
| `verifiedTeacher` | boolean | - | Represents whether a Google Workspace for Education user's domain administrator has explicitly verified them as being a teacher. This field is always false if the user is not a member of a Google Workspace for Education domain. Read-only |
| `id` | string | - | Identifier of the user. Read-only. |
| `photoUrl` | string | - | URL of user's profile photo. Must request `https://www.googleapis.com/auth/classroom.profile.photos` scope for this field to be populated in a response body. Read-only. |
| `permissions` | Array of [`GlobalPermission`](#globalpermission) | - | Global permissions of the user. Read-only. |
| `name` | [`Name`](#name) | - | Name of the user. Read-only. |
| `emailAddress` | string | - | Email address of the user. Must request `https://www.googleapis.com/auth/classroom.profile.emails` scope for this field to be populated in a response body. Read-only. |


---

## YouTubeVideo
**Type:** `object`

YouTube video item.

| Field | Type | Format / Enum | Description |
|---|---|---|---|
| `alternateLink` | string | - | URL that can be used to view the YouTube video. Read-only. |
| `thumbnailUrl` | string | - | URL of a thumbnail image of the YouTube video. Read-only. |
| `title` | string | - | Title of the YouTube video. Read-only. |
| `id` | string | - | YouTube API resource ID. |


---
