-- Phase 4.5B: source-safe prerequisite references for Zarqa University AI Plan 12.
-- Only a raw value containing exactly one course code is modeled. Multi-code
-- source syntax remains unmodeled until its AND/OR semantics are verified.

begin;

insert into public.courses (
  university_id,
  course_code,
  name_ar,
  name_en,
  catalog_status,
  active
) values
  ('10000000-0000-0000-0000-000000000001', '0200150', null, null, 'referenced_only', true),
  ('10000000-0000-0000-0000-000000000001', '0200151', null, null, 'referenced_only', true),
  ('10000000-0000-0000-0000-000000000001', '0201001', null, null, 'referenced_only', true),
  ('10000000-0000-0000-0000-000000000001', '0202001', null, null, 'referenced_only', true),
  ('10000000-0000-0000-0000-000000000001', '0300103', null, null, 'referenced_only', true),
  ('10000000-0000-0000-0000-000000000001', '0301241', null, null, 'referenced_only', true);

create temporary table _ai_plan12_verified_prerequisites (
  target_course_code text primary key,
  prerequisite_course_code text not null
) on commit drop;

insert into _ai_plan12_verified_prerequisites values
  ('0300220', '0300153'),
  ('1501110', '0300153'),
  ('1501112', '1501110'),
  ('1501221', '1501112'),
  ('0200215', '0200106'),
  ('1501212', '1501222'),
  ('1501385', '1501112'),
  ('1505211', '1501112'),
  ('1505303', '0300220'),
  ('1505351', '1505201'),
  ('1505365', '1501222'),
  ('1505414', '1505311'),
  ('1505480', '1501222'),
  ('1505482', '1505381'),
  ('1506493', '1501340'),
  ('1501111', '0300153'),
  ('1501113', '1501111'),
  ('1501222', '1501112'),
  ('1501321', '1501221'),
  ('1501340', '1501112'),
  ('1501430', '1501221'),
  ('1503270', '0300153'),
  ('1505101', '1501110'),
  ('1505201', '0300153'),
  ('1505223', '1505101'),
  ('1505333', '1501222'),
  ('1505381', '1505201'),
  ('1505415', '1505311'),
  ('1505441', '1505311'),
  ('1505468', '1505467'),
  ('1506180', '1501110'),
  ('1506181', '1501111');

insert into public.course_dependency_groups (
  study_plan_course_id,
  dependency_type,
  group_number,
  verification_status
)
select
  target_plan_course.id,
  'prerequisite',
  1,
  'verified'
from _ai_plan12_verified_prerequisites seed
join public.courses target_course
  on target_course.university_id = '10000000-0000-0000-0000-000000000001'
 and target_course.course_code = seed.target_course_code
join public.study_plan_courses target_plan_course
  on target_plan_course.study_plan_id = '10000000-0000-0000-0000-000000000005'
 and target_plan_course.course_id = target_course.id;

insert into public.course_dependency_options (
  dependency_group_id,
  dependency_course_id,
  verification_status
)
select
  dependency_group.id,
  prerequisite_course.id,
  case prerequisite_course.catalog_status
    when 'referenced_only' then 'referenced_only'
    else 'verified'
  end
from _ai_plan12_verified_prerequisites seed
join public.courses target_course
  on target_course.university_id = '10000000-0000-0000-0000-000000000001'
 and target_course.course_code = seed.target_course_code
join public.study_plan_courses target_plan_course
  on target_plan_course.study_plan_id = '10000000-0000-0000-0000-000000000005'
 and target_plan_course.course_id = target_course.id
join public.course_dependency_groups dependency_group
  on dependency_group.study_plan_course_id = target_plan_course.id
 and dependency_group.dependency_type = 'prerequisite'
 and dependency_group.group_number = 1
join public.courses prerequisite_course
  on prerequisite_course.university_id = '10000000-0000-0000-0000-000000000001'
 and prerequisite_course.course_code = seed.prerequisite_course_code;

update public.study_plan_courses target_plan_course
set prerequisite_logic_status = 'verified'
from _ai_plan12_verified_prerequisites seed
join public.courses target_course
  on target_course.university_id = '10000000-0000-0000-0000-000000000001'
 and target_course.course_code = seed.target_course_code
where target_plan_course.study_plan_id = '10000000-0000-0000-0000-000000000005'
  and target_plan_course.course_id = target_course.id;

commit;
